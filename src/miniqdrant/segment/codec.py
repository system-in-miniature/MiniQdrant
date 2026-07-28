from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import tempfile
import zlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from miniqdrant.config import (
    CollectionConfig,
    config_from_dict,
    config_to_dict,
)
from miniqdrant.errors import CorruptionError
from miniqdrant.filters.index import PayloadSchema
from miniqdrant.ids import PointId, canonicalize_point_id, point_id_sort_key
from miniqdrant.index.hnsw import HnswGraph, HnswIndex
from miniqdrant.json_values import freeze_json_object, thaw_json
from miniqdrant.models import StoredPoint
from miniqdrant.persistence.fsync import fsync_directory
from miniqdrant.segment.immutable import ImmutableSegment

_MAGIC = b"MQSG"
_VERSION = 1
_HEADER = struct.Struct(">4sBI")
_CRC = struct.Struct(">I")
_FILES = (
    "points.bin",
    "payloads.bin",
    "versions.bin",
    "deleted.bin",
    "hnsw.bin",
    "payload-indexes.bin",
)


@dataclass(frozen=True, slots=True)
class SegmentImage:
    segment_id: str
    config: CollectionConfig
    records: tuple[StoredPoint, ...]
    payload_schemas: Mapping[str, PayloadSchema]
    indexed: bool
    hnsw_graph: HnswGraph | None

    @classmethod
    def build(
        cls,
        *,
        segment_id: str,
        config: CollectionConfig,
        records: Iterable[StoredPoint],
        payload_schemas: Mapping[str, PayloadSchema],
        indexed: bool,
    ) -> SegmentImage:
        ordered = tuple(sorted(records, key=lambda point: point_id_sort_key(point.id)))
        live = tuple(point for point in ordered if not point.deleted)
        graph = (
            HnswIndex.build(live, distance=config.distance, config=config.hnsw).export_graph()
            if indexed and live
            else None
        )
        return cls(
            segment_id,
            config,
            ordered,
            dict(payload_schemas),
            indexed,
            graph,
        )

    def to_segment(self) -> ImmutableSegment:
        return ImmutableSegment.build(
            self.config,
            self.records,
            payload_schemas=self.payload_schemas,
            indexed=self.indexed,
        )

    def semantic_fingerprint(self) -> str:
        payload = {
            "segment_id": self.segment_id,
            "config": config_to_dict(self.config),
            "records": [_encode_record(record) for record in self.records],
            "payload_schemas": {
                path: schema.value for path, schema in sorted(self.payload_schemas.items())
            },
            "indexed": self.indexed,
            "hnsw": _encode_graph(self.hnsw_graph),
        }
        return hashlib.sha256(_canonical_json(payload)).hexdigest()


class SegmentCodec:
    @staticmethod
    def write_atomic(root: str | Path, image: SegmentImage) -> Path:
        directory = Path(root)
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / image.segment_id
        if target.exists():
            raise FileExistsError(target)
        temporary = Path(tempfile.mkdtemp(prefix=f".{image.segment_id}-", dir=directory))
        try:
            payloads = _image_files(image)
            checksums: dict[str, str] = {}
            for filename, payload in payloads.items():
                path = temporary / filename
                encoded = _encode_blob(payload)
                _write_fsynced(path, encoded)
                checksums[filename] = hashlib.sha256(encoded).hexdigest()
            meta = {
                "format_version": _VERSION,
                "segment_id": image.segment_id,
                "config": config_to_dict(image.config),
                "indexed": image.indexed,
                "checksums": checksums,
            }
            _write_fsynced(temporary / "meta.json", _canonical_json(meta))
            fsync_directory(temporary)
            os.replace(temporary, target)
            fsync_directory(directory)
            return target
        except BaseException:
            if temporary.exists():
                shutil.rmtree(temporary)
            raise

    @staticmethod
    def read(path: str | Path) -> SegmentImage:
        directory = Path(path)
        try:
            meta = json.loads((directory / "meta.json").read_bytes())
            if meta["format_version"] != _VERSION:
                raise CorruptionError("unsupported segment format version")
            checksums = meta["checksums"]
            payloads: dict[str, object] = {}
            for filename in _FILES:
                encoded = (directory / filename).read_bytes()
                if hashlib.sha256(encoded).hexdigest() != checksums[filename]:
                    raise CorruptionError(f"segment checksum mismatch: {filename}")
                payloads[filename] = _decode_blob(encoded)
            return _decode_image(meta, payloads)
        except CorruptionError:
            raise
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise CorruptionError(f"invalid segment at {directory}") from error


def _image_files(image: SegmentImage) -> dict[str, object]:
    records = image.records
    return {
        "points.bin": [
            {"id": _encode_id(point.id), "vector": list(point.vector)}
            for point in records
            if not point.deleted
        ],
        "payloads.bin": [
            {"id": _encode_id(point.id), "payload": thaw_json(point.payload)}
            for point in records
            if not point.deleted
        ],
        "versions.bin": [
            {"id": _encode_id(point.id), "version": point.version} for point in records
        ],
        "deleted.bin": [
            _encode_id(point.id) for point in records if point.deleted
        ],
        "hnsw.bin": _encode_graph(image.hnsw_graph),
        "payload-indexes.bin": {
            path: schema.value for path, schema in sorted(image.payload_schemas.items())
        },
    }


def _decode_image(meta: dict[str, object], payloads: dict[str, object]) -> SegmentImage:
    point_values = {
        _decode_id(item["id"]): tuple(item["vector"])
        for item in payloads["points.bin"]
    }
    payload_values = {
        _decode_id(item["id"]): freeze_json_object(item["payload"])
        for item in payloads["payloads.bin"]
    }
    deleted = {_decode_id(value) for value in payloads["deleted.bin"]}
    records = tuple(
        StoredPoint(
            id=(point_id := _decode_id(item["id"])),
            vector=() if point_id in deleted else point_values[point_id],
            payload=freeze_json_object({}) if point_id in deleted else payload_values[point_id],
            version=int(item["version"]),
            deleted=point_id in deleted,
        )
        for item in payloads["versions.bin"]
    )
    schemas = {
        path: PayloadSchema(schema)
        for path, schema in payloads["payload-indexes.bin"].items()
    }
    return SegmentImage(
        segment_id=str(meta["segment_id"]),
        config=config_from_dict(meta["config"]),
        records=records,
        payload_schemas=schemas,
        indexed=bool(meta["indexed"]),
        hnsw_graph=_decode_graph(payloads["hnsw.bin"]),
    )


def _encode_blob(value: object) -> bytes:
    payload = _canonical_json(value)
    body = _HEADER.pack(_MAGIC, _VERSION, len(payload)) + payload
    return body + _CRC.pack(zlib.crc32(body))


def _decode_blob(value: bytes) -> object:
    if len(value) < _HEADER.size + _CRC.size:
        raise CorruptionError("segment blob is truncated")
    magic, version, length = _HEADER.unpack_from(value)
    expected_length = _HEADER.size + length + _CRC.size
    if magic != _MAGIC or version != _VERSION or len(value) != expected_length:
        raise CorruptionError("invalid segment blob header")
    body = value[: _HEADER.size + length]
    expected_crc = _CRC.unpack_from(value, _HEADER.size + length)[0]
    if zlib.crc32(body) != expected_crc:
        raise CorruptionError("segment blob checksum mismatch")
    try:
        return json.loads(value[_HEADER.size : _HEADER.size + length])
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CorruptionError("invalid segment blob JSON") from error


def _encode_record(record: StoredPoint) -> dict[str, object]:
    return {
        "id": _encode_id(record.id),
        "vector": list(record.vector),
        "payload": thaw_json(record.payload),
        "version": record.version,
        "deleted": record.deleted,
    }


def _encode_graph(graph: HnswGraph | None) -> object:
    if graph is None:
        return None
    return {
        "entry_point": None if graph.entry_point is None else _encode_id(graph.entry_point),
        "max_level": graph.max_level,
        "levels": [
            [_encode_id(point_id), level]
            for point_id, level in sorted(
                graph.levels.items(),
                key=lambda item: point_id_sort_key(item[0]),
            )
        ],
        "layers": [
            [
                layer,
                [
                    [
                        _encode_id(point_id),
                        [_encode_id(neighbor) for neighbor in neighbors],
                    ]
                    for point_id, neighbors in adjacency.items()
                ],
            ]
            for layer, adjacency in graph.layers.items()
        ],
    }


def _decode_graph(value: object) -> HnswGraph | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("HNSW graph must be an object")
    levels = {_decode_id(item[0]): int(item[1]) for item in value["levels"]}
    layers = {
        int(layer): {
            _decode_id(item[0]): tuple(_decode_id(neighbor) for neighbor in item[1])
            for item in adjacency
        }
        for layer, adjacency in value["layers"]
    }
    entry = value["entry_point"]
    return HnswGraph(
        entry_point=None if entry is None else _decode_id(entry),
        max_level=int(value["max_level"]),
        levels=levels,
        layers=layers,
    )


def _encode_id(value: PointId) -> dict[str, object]:
    if isinstance(value, int):
        return {"kind": "int", "value": value}
    return {"kind": "uuid", "value": str(value)}


def _decode_id(value: object) -> PointId:
    if not isinstance(value, dict):
        raise ValueError("point id must be an object")
    if value.get("kind") == "int":
        return canonicalize_point_id(value.get("value"))
    if value.get("kind") == "uuid":
        return UUID(str(value.get("value")))
    raise ValueError("unknown point id encoding")


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _write_fsynced(path: Path, value: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())
