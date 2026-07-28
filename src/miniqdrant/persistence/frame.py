from __future__ import annotations

import os
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

from miniqdrant.errors import CorruptionError

MAGIC = b"MQWL"
FORMAT_VERSION = 1
MAX_FRAME_BYTES = 256 * 1024 * 1024
_HEADER = struct.Struct(">4sBI")
_BODY_PREFIX = struct.Struct(">QB")
_CRC = struct.Struct(">I")


@dataclass(frozen=True, slots=True)
class DecodedFrame:
    sequence: int
    kind: int
    payload: bytes


def encode_frame(sequence: int, kind: int, payload: bytes) -> bytes:
    body = _BODY_PREFIX.pack(sequence, kind) + payload
    checksum = zlib.crc32(body)
    return _HEADER.pack(MAGIC, FORMAT_VERSION, len(body)) + body + _CRC.pack(checksum)


def scan_frames(path: Path, *, repair_tail: bool) -> tuple[DecodedFrame, ...]:
    data = path.read_bytes()
    frames: list[DecodedFrame] = []
    offset = 0
    last_valid = 0
    while offset < len(data):
        frame_start = offset
        if len(data) - offset < _HEADER.size:
            return _repair_or_raise(path, frames, last_valid, repair_tail)
        magic, version, body_length = _HEADER.unpack_from(data, offset)
        offset += _HEADER.size
        if magic != MAGIC or version != FORMAT_VERSION or body_length > MAX_FRAME_BYTES:
            raise CorruptionError(f"invalid WAL frame header at byte {frame_start}")
        frame_end = offset + body_length + _CRC.size
        if frame_end > len(data):
            return _repair_or_raise(path, frames, last_valid, repair_tail)
        body = data[offset : offset + body_length]
        expected_crc = _CRC.unpack_from(data, offset + body_length)[0]
        actual_crc = zlib.crc32(body)
        if expected_crc != actual_crc:
            if repair_tail and frame_end == len(data):
                _truncate(path, last_valid)
                return tuple(frames)
            raise CorruptionError(f"WAL checksum mismatch at byte {frame_start}")
        if len(body) < _BODY_PREFIX.size:
            if repair_tail and frame_end == len(data):
                _truncate(path, last_valid)
                return tuple(frames)
            raise CorruptionError(f"WAL body is too short at byte {frame_start}")
        sequence, kind = _BODY_PREFIX.unpack_from(body)
        frames.append(DecodedFrame(sequence, kind, body[_BODY_PREFIX.size :]))
        offset = frame_end
        last_valid = offset
    return tuple(frames)


def _repair_or_raise(
    path: Path,
    frames: list[DecodedFrame],
    last_valid: int,
    repair_tail: bool,
) -> tuple[DecodedFrame, ...]:
    if not repair_tail:
        raise CorruptionError(f"incomplete WAL tail after byte {last_valid}")
    _truncate(path, last_valid)
    return tuple(frames)


def _truncate(path: Path, size: int) -> None:
    with path.open("r+b") as stream:
        stream.truncate(size)
        stream.flush()
        os.fsync(stream.fileno())

