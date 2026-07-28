from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from miniqdrant.config import CollectionConfig, config_from_dict, config_to_dict
from miniqdrant.errors import CorruptionError
from miniqdrant.filters.index import PayloadSchema
from miniqdrant.persistence.fsync import fsync_directory


@dataclass(frozen=True, slots=True)
class CollectionMetadata:
    name: str
    config: CollectionConfig
    payload_schemas: dict[str, PayloadSchema]


def write_collection_metadata(path: Path, metadata: CollectionMetadata) -> None:
    payload = {
        "name": metadata.name,
        "config": config_to_dict(metadata.config),
        "payload_schemas": {
            field: schema.value
            for field, schema in sorted(metadata.payload_schemas.items())
        },
    }
    canonical = _canonical_json(payload)
    envelope = {
        "format_version": 1,
        "payload": payload,
        "sha256": hashlib.sha256(canonical).hexdigest(),
    }
    temporary = path.with_suffix(".json.tmp")
    with temporary.open("wb") as stream:
        stream.write(_canonical_json(envelope))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    fsync_directory(path.parent)


def read_collection_metadata(path: Path) -> CollectionMetadata:
    try:
        envelope = json.loads(path.read_bytes())
        if envelope["format_version"] != 1:
            raise CorruptionError("unsupported collection metadata format")
        payload = envelope["payload"]
        if hashlib.sha256(_canonical_json(payload)).hexdigest() != envelope["sha256"]:
            raise CorruptionError("collection metadata checksum mismatch")
        return CollectionMetadata(
            name=str(payload["name"]),
            config=config_from_dict(payload["config"]),
            payload_schemas={
                field: PayloadSchema(schema)
                for field, schema in payload["payload_schemas"].items()
            },
        )
    except CorruptionError:
        raise
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise CorruptionError(f"invalid collection metadata: {path}") from error


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
