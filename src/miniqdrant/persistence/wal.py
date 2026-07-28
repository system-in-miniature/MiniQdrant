from __future__ import annotations

import json
import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from uuid import UUID

from miniqdrant.errors import ClosedResourceError, CorruptionError
from miniqdrant.ids import PointId, canonicalize_point_id
from miniqdrant.json_values import thaw_json
from miniqdrant.models import Point
from miniqdrant.persistence.frame import DecodedFrame, encode_frame, scan_frames
from miniqdrant.persistence.fsync import fsync_directory


class Durability(StrEnum):
    ALWAYS = "always"
    INTERVAL = "interval"
    MANUAL = "manual"


@dataclass(frozen=True, slots=True)
class UpsertOperation:
    points: tuple[Point, ...]

    def __post_init__(self) -> None:
        if not self.points:
            raise ValueError("upsert operation must contain points")
        object.__setattr__(self, "points", tuple(self.points))


@dataclass(frozen=True, slots=True)
class DeleteOperation:
    point_ids: tuple[PointId, ...]

    def __post_init__(self) -> None:
        if not self.point_ids:
            raise ValueError("delete operation must contain point ids")
        object.__setattr__(
            self,
            "point_ids",
            tuple(canonicalize_point_id(value) for value in self.point_ids),
        )


type Operation = UpsertOperation | DeleteOperation


@dataclass(frozen=True, slots=True)
class WalRecord:
    sequence: int
    operation: Operation


class Wal:
    _FILENAME = "00000000000000000001.wal"

    def __init__(self, path: Path, durability: Durability) -> None:
        self._path = path
        self._durability = Durability(durability)
        self._active_path = path / self._FILENAME
        frames = scan_frames(self._active_path, repair_tail=True)
        _validate_sequences(frames)
        self._sequence = frames[-1].sequence if frames else 0
        self._stream = self._active_path.open("ab", buffering=0)
        self._closed = False

    @classmethod
    def create(
        cls,
        path: str | Path,
        durability: Durability = Durability.ALWAYS,
    ) -> Wal:
        directory = Path(path)
        directory.mkdir(parents=True, exist_ok=False)
        active_path = directory / cls._FILENAME
        active_path.touch()
        fsync_directory(directory)
        return cls(directory, durability)

    @classmethod
    def open(
        cls,
        path: str | Path,
        durability: Durability = Durability.ALWAYS,
    ) -> Wal:
        directory = Path(path)
        active_path = directory / cls._FILENAME
        if not active_path.is_file():
            raise CorruptionError(f"WAL file is missing: {active_path}")
        return cls(directory, durability)

    @property
    def active_path(self) -> Path:
        return self._active_path

    @property
    def last_sequence(self) -> int:
        return self._sequence

    def append(self, operation: Operation) -> WalRecord:
        self._ensure_open()
        sequence = self._sequence + 1
        kind, payload = _encode_operation(operation)
        self._stream.write(encode_frame(sequence, kind, payload))
        if self._durability is Durability.ALWAYS:
            os.fsync(self._stream.fileno())
        self._sequence = sequence
        return WalRecord(sequence, operation)

    def replay(self, *, after_sequence: int = 0) -> tuple[WalRecord, ...]:
        self._ensure_open()
        return tuple(
            WalRecord(frame.sequence, _decode_operation(frame))
            for frame in scan_frames(self._active_path, repair_tail=False)
            if frame.sequence > after_sequence
        )

    def flush(self) -> None:
        self._ensure_open()
        os.fsync(self._stream.fileno())

    def close(self) -> None:
        if self._closed:
            return
        self._stream.close()
        self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise ClosedResourceError("WAL is closed")


def _encode_operation(operation: Operation) -> tuple[int, bytes]:
    if isinstance(operation, UpsertOperation):
        value = {
            "points": [
                {
                    "id": _encode_id(point.id),
                    "vector": list(point.vector),
                    "payload": thaw_json(point.payload),
                }
                for point in operation.points
            ]
        }
        kind = 1
    else:
        value = {"point_ids": [_encode_id(point_id) for point_id in operation.point_ids]}
        kind = 2
    payload = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return kind, payload


def _decode_operation(frame: DecodedFrame) -> Operation:
    try:
        value = json.loads(frame.payload)
        if frame.kind == 1:
            return UpsertOperation(
                tuple(
                    Point(
                        _decode_id(point["id"]),
                        tuple(point["vector"]),
                        point["payload"],
                    )
                    for point in value["points"]
                )
            )
        if frame.kind == 2:
            return DeleteOperation(
                tuple(_decode_id(point_id) for point_id in value["point_ids"])
            )
    except (KeyError, TypeError, ValueError, UnicodeDecodeError) as error:
        raise CorruptionError(f"invalid WAL operation at sequence {frame.sequence}") from error
    raise CorruptionError(f"unknown WAL operation kind {frame.kind}")


def _encode_id(value: object) -> dict[str, object]:
    point_id = canonicalize_point_id(value)
    if isinstance(point_id, int):
        return {"kind": "int", "value": point_id}
    return {"kind": "uuid", "value": str(point_id)}


def _decode_id(value: object) -> PointId:
    if not isinstance(value, dict):
        raise ValueError("point id encoding must be an object")
    if value.get("kind") == "int":
        return canonicalize_point_id(value.get("value"))
    if value.get("kind") == "uuid":
        return UUID(str(value.get("value")))
    raise ValueError("unknown point id encoding")


def _validate_sequences(frames: tuple[DecodedFrame, ...]) -> None:
    expected = 1
    for frame in frames:
        if frame.sequence != expected:
            raise CorruptionError(
                f"WAL sequence mismatch: expected {expected}, got {frame.sequence}"
            )
        expected += 1

