# Stage 09 · 分帧预写日志

### 目标

实现分帧预写日志，并能从可执行反例、运行时状态与关键语句解释其边界。

??? note "交付文件"
    - `src/miniqdrant/persistence/__init__.py`
    - `src/miniqdrant/persistence/frame.py`
    - `src/miniqdrant/persistence/fsync.py`
    - `src/miniqdrant/persistence/wal.py`
    - `tests/reliability/test_wal_replay.py`
    - `tests/reliability/test_wal_tail.py`
    - `tests/storage/test_wal_codec.py`

### 当前遇到的问题

已确认操作需要有序、带校验和的 Frame，使截断或尾部损坏后仍能恢复有效前缀。

### 测试契约

#### 先看会坏在哪里

聚焦测试让分帧预写日志经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

??? note "文件差异：tests/reliability/test_wal_replay.py"
    ```diff
    diff --git a/tests/reliability/test_wal_replay.py b/tests/reliability/test_wal_replay.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..2072541e80bd66b82783df58b1f53374a27e398c
    --- /dev/null
    +++ b/tests/reliability/test_wal_replay.py
    @@ -0,0 +1,14 @@
    +from __future__ import annotations
    +
    +from miniqdrant.models import Point
    +from miniqdrant.persistence.wal import DeleteOperation, UpsertOperation, Wal
    +
    +
    +def test_replay_can_start_after_manifest_boundary(tmp_path) -> None:
    +    wal = Wal.create(tmp_path / "wal")
    +    wal.append(UpsertOperation((Point(1, (1.0,), {}),)))
    +    wal.append(DeleteOperation((1,)))
    +    third = wal.append(UpsertOperation((Point(1, (2.0,), {}),)))
    +
    +    assert list(wal.replay(after_sequence=2)) == [third]
    +
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让分帧预写日志经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert list(wal.replay(after_sequence=2)) == [third]
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/reliability/test_wal_tail.py"
    ```diff
    diff --git a/tests/reliability/test_wal_tail.py b/tests/reliability/test_wal_tail.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..e76fdc34527929de688324e7210e52521fffef2d
    --- /dev/null
    +++ b/tests/reliability/test_wal_tail.py
    @@ -0,0 +1,59 @@
    +from __future__ import annotations
    +
    +import os
    +
    +import pytest
    +
    +from miniqdrant.errors import CorruptionError
    +from miniqdrant.persistence.wal import DeleteOperation, Wal
    +
    +
    +def populated_wal(tmp_path) -> Wal:
    +    wal = Wal.create(tmp_path / "wal")
    +    wal.append(DeleteOperation((1,)))
    +    wal.append(DeleteOperation((2,)))
    +    wal.flush()
    +    return wal
    +
    +
    +def test_incomplete_active_tail_is_truncated(tmp_path) -> None:
    +    wal = populated_wal(tmp_path)
    +    original_size = wal.active_path.stat().st_size
    +    wal.close()
    +    with (tmp_path / "wal" / "00000000000000000001.wal").open("ab") as stream:
    +        stream.write(b"\x00\x00\x00")
    +
    +    reopened = Wal.open(tmp_path / "wal")
    +
    +    assert [item.sequence for item in reopened.replay()] == [1, 2]
    +    assert reopened.active_path.stat().st_size == original_size
    +
    +
    +def test_corrupt_last_frame_is_truncated(tmp_path) -> None:
    +    wal = populated_wal(tmp_path)
    +    path = wal.active_path
    +    wal.close()
    +    with path.open("r+b") as stream:
    +        stream.seek(-1, os.SEEK_END)
    +        byte = stream.read(1)
    +        stream.seek(-1, os.SEEK_END)
    +        stream.write(bytes([byte[0] ^ 0xFF]))
    +
    +    reopened = Wal.open(tmp_path / "wal")
    +
    +    assert [item.sequence for item in reopened.replay()] == [1]
    +
    +
    +def test_corruption_before_active_tail_is_fatal(tmp_path) -> None:
    +    wal = populated_wal(tmp_path)
    +    path = wal.active_path
    +    wal.close()
    +    with path.open("r+b") as stream:
    +        stream.seek(20)
    +        byte = stream.read(1)
    +        stream.seek(20)
    +        stream.write(bytes([byte[0] ^ 0xFF]))
    +
    +    with pytest.raises(CorruptionError):
    +        Wal.open(tmp_path / "wal")
    +
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让分帧预写日志经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert list(wal.replay(after_sequence=2)) == [third]
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/storage/test_wal_codec.py"
    ```diff
    diff --git a/tests/storage/test_wal_codec.py b/tests/storage/test_wal_codec.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..c1fea1ed3a65d888e33e673eb6028b013e8ed587
    --- /dev/null
    +++ b/tests/storage/test_wal_codec.py
    @@ -0,0 +1,49 @@
    +from __future__ import annotations
    +
    +from uuid import UUID
    +
    +from miniqdrant.models import Point
    +from miniqdrant.persistence.wal import (
    +    DeleteOperation,
    +    Durability,
    +    UpsertOperation,
    +    Wal,
    +)
    +
    +
    +def test_wal_round_trip_is_binary_safe(tmp_path) -> None:
    +    wal = Wal.create(tmp_path / "wal", durability=Durability.ALWAYS)
    +    operation = UpsertOperation(
    +        (
    +            Point(1, (1.0, 2.0), {"text": "雪", "raw": "a\u0000b"}),
    +            Point(UUID(int=2), (3.0, 4.0), {"nested": [1, True, None]}),
    +        )
    +    )
    +
    +    record = wal.append(operation)
    +    wal.close()
    +    reopened = Wal.open(tmp_path / "wal", durability=Durability.ALWAYS)
    +
    +    assert record.sequence == 1
    +    assert list(reopened.replay()) == [record]
    +
    +
    +def test_delete_operation_round_trip(tmp_path) -> None:
    +    wal = Wal.create(tmp_path / "wal", durability=Durability.MANUAL)
    +
    +    first = wal.append(DeleteOperation((1, UUID(int=4))))
    +    wal.flush()
    +    wal.close()
    +
    +    assert list(Wal.open(tmp_path / "wal").replay()) == [first]
    +
    +
    +def test_sequences_continue_after_reopen(tmp_path) -> None:
    +    wal = Wal.create(tmp_path / "wal")
    +    wal.append(DeleteOperation((1,)))
    +    wal.close()
    +
    +    reopened = Wal.open(tmp_path / "wal")
    +
    +    assert reopened.append(DeleteOperation((2,))).sequence == 2
    +
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让分帧预写日志经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert list(wal.replay(after_sequence=2)) == [third]
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是分帧预写日志。已确认操作需要有序、带校验和的 Frame，使截断或尾部损坏后仍能恢复有效前缀。

### 为什么需要这个机制

已确认操作需要有序、带校验和的 Frame，使截断或尾部损坏后仍能恢复有效前缀。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

Mutation 只有完整 Frame 持久后才能发布，恢复绝不跳过损坏去虚构后续历史。

### 机制板块

#### 分帧预写日志机制

Mutation 只有完整 Frame 持久后才能发布，恢复绝不跳过损坏去虚构后续历史。

??? note "文件差异：src/miniqdrant/persistence/frame.py"
    ```diff
    diff --git a/src/miniqdrant/persistence/frame.py b/src/miniqdrant/persistence/frame.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..e56facd7205cf19f40532010d4d33fe3be7d67ad
    --- /dev/null
    +++ b/src/miniqdrant/persistence/frame.py
    @@ -0,0 +1,85 @@
    +from __future__ import annotations
    +
    +import os
    +import struct
    +import zlib
    +from dataclasses import dataclass
    +from pathlib import Path
    +
    +from miniqdrant.errors import CorruptionError
    +
    +MAGIC = b"MQWL"
    +FORMAT_VERSION = 1
    +MAX_FRAME_BYTES = 256 * 1024 * 1024
    +_HEADER = struct.Struct(">4sBI")
    +_BODY_PREFIX = struct.Struct(">QB")
    +_CRC = struct.Struct(">I")
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class DecodedFrame:
    +    sequence: int
    +    kind: int
    +    payload: bytes
    +
    +
    +def encode_frame(sequence: int, kind: int, payload: bytes) -> bytes:
    +    body = _BODY_PREFIX.pack(sequence, kind) + payload
    +    checksum = zlib.crc32(body)
    +    return _HEADER.pack(MAGIC, FORMAT_VERSION, len(body)) + body + _CRC.pack(checksum)
    +
    +
    +def scan_frames(path: Path, *, repair_tail: bool) -> tuple[DecodedFrame, ...]:
    +    data = path.read_bytes()
    +    frames: list[DecodedFrame] = []
    +    offset = 0
    +    last_valid = 0
    +    while offset < len(data):
    +        frame_start = offset
    +        if len(data) - offset < _HEADER.size:
    +            return _repair_or_raise(path, frames, last_valid, repair_tail)
    +        magic, version, body_length = _HEADER.unpack_from(data, offset)
    +        offset += _HEADER.size
    +        if magic != MAGIC or version != FORMAT_VERSION or body_length > MAX_FRAME_BYTES:
    +            raise CorruptionError(f"invalid WAL frame header at byte {frame_start}")
    +        frame_end = offset + body_length + _CRC.size
    +        if frame_end > len(data):
    +            return _repair_or_raise(path, frames, last_valid, repair_tail)
    +        body = data[offset : offset + body_length]
    +        expected_crc = _CRC.unpack_from(data, offset + body_length)[0]
    +        actual_crc = zlib.crc32(body)
    +        if expected_crc != actual_crc:
    +            if repair_tail and frame_end == len(data):
    +                _truncate(path, last_valid)
    +                return tuple(frames)
    +            raise CorruptionError(f"WAL checksum mismatch at byte {frame_start}")
    +        if len(body) < _BODY_PREFIX.size:
    +            if repair_tail and frame_end == len(data):
    +                _truncate(path, last_valid)
    +                return tuple(frames)
    +            raise CorruptionError(f"WAL body is too short at byte {frame_start}")
    +        sequence, kind = _BODY_PREFIX.unpack_from(body)
    +        frames.append(DecodedFrame(sequence, kind, body[_BODY_PREFIX.size :]))
    +        offset = frame_end
    +        last_valid = offset
    +    return tuple(frames)
    +
    +
    +def _repair_or_raise(
    +    path: Path,
    +    frames: list[DecodedFrame],
    +    last_valid: int,
    +    repair_tail: bool,
    +) -> tuple[DecodedFrame, ...]:
    +    if not repair_tail:
    +        raise CorruptionError(f"incomplete WAL tail after byte {last_valid}")
    +    _truncate(path, last_valid)
    +    return tuple(frames)
    +
    +
    +def _truncate(path: Path, size: int) -> None:
    +    with path.open("r+b") as stream:
    +        stream.truncate(size)
    +        stream.flush()
    +        os.fsync(stream.fileno())
    +
    ```

??? note "文件差异：src/miniqdrant/persistence/fsync.py"
    ```diff
    diff --git a/src/miniqdrant/persistence/fsync.py b/src/miniqdrant/persistence/fsync.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..446848a26629b3e20566e43d457c86efd1a9a442
    --- /dev/null
    +++ b/src/miniqdrant/persistence/fsync.py
    @@ -0,0 +1,17 @@
    +from __future__ import annotations
    +
    +import os
    +from pathlib import Path
    +
    +
    +def fsync_file_descriptor(file_descriptor: int) -> None:
    +    os.fsync(file_descriptor)
    +
    +
    +def fsync_directory(path: Path) -> None:
    +    descriptor = os.open(path, os.O_RDONLY)
    +    try:
    +        os.fsync(descriptor)
    +    finally:
    +        os.close(descriptor)
    +
    ```

??? note "文件差异：src/miniqdrant/persistence/wal.py"
    ```diff
    diff --git a/src/miniqdrant/persistence/wal.py b/src/miniqdrant/persistence/wal.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..2f633d2130ebc5e2310bfdf4461015bd1242fb53
    --- /dev/null
    +++ b/src/miniqdrant/persistence/wal.py
    @@ -0,0 +1,210 @@
    +from __future__ import annotations
    +
    +import json
    +import os
    +from dataclasses import dataclass
    +from enum import StrEnum
    +from pathlib import Path
    +from uuid import UUID
    +
    +from miniqdrant.errors import ClosedResourceError, CorruptionError
    +from miniqdrant.ids import PointId, canonicalize_point_id
    +from miniqdrant.json_values import thaw_json
    +from miniqdrant.models import Point
    +from miniqdrant.persistence.frame import DecodedFrame, encode_frame, scan_frames
    +from miniqdrant.persistence.fsync import fsync_directory
    +
    +
    +class Durability(StrEnum):
    +    ALWAYS = "always"
    +    INTERVAL = "interval"
    +    MANUAL = "manual"
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class UpsertOperation:
    +    points: tuple[Point, ...]
    +
    +    def __post_init__(self) -> None:
    +        if not self.points:
    +            raise ValueError("upsert operation must contain points")
    +        object.__setattr__(self, "points", tuple(self.points))
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class DeleteOperation:
    +    point_ids: tuple[PointId, ...]
    +
    +    def __post_init__(self) -> None:
    +        if not self.point_ids:
    +            raise ValueError("delete operation must contain point ids")
    +        object.__setattr__(
    +            self,
    +            "point_ids",
    +            tuple(canonicalize_point_id(value) for value in self.point_ids),
    +        )
    +
    +
    +type Operation = UpsertOperation | DeleteOperation
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class WalRecord:
    +    sequence: int
    +    operation: Operation
    +
    +
    +class Wal:
    +    _FILENAME = "00000000000000000001.wal"
    +
    +    def __init__(self, path: Path, durability: Durability) -> None:
    +        self._path = path
    +        self._durability = Durability(durability)
    +        self._active_path = path / self._FILENAME
    +        frames = scan_frames(self._active_path, repair_tail=True)
    +        _validate_sequences(frames)
    +        self._sequence = frames[-1].sequence if frames else 0
    +        self._stream = self._active_path.open("ab", buffering=0)
    +        self._closed = False
    +
    +    @classmethod
    +    def create(
    +        cls,
    +        path: str | Path,
    +        durability: Durability = Durability.ALWAYS,
    +    ) -> Wal:
    +        directory = Path(path)
    +        directory.mkdir(parents=True, exist_ok=False)
    +        active_path = directory / cls._FILENAME
    +        active_path.touch()
    +        fsync_directory(directory)
    +        return cls(directory, durability)
    +
    +    @classmethod
    +    def open(
    +        cls,
    +        path: str | Path,
    +        durability: Durability = Durability.ALWAYS,
    +    ) -> Wal:
    +        directory = Path(path)
    +        active_path = directory / cls._FILENAME
    +        if not active_path.is_file():
    +            raise CorruptionError(f"WAL file is missing: {active_path}")
    +        return cls(directory, durability)
    +
    +    @property
    +    def active_path(self) -> Path:
    +        return self._active_path
    +
    +    @property
    +    def last_sequence(self) -> int:
    +        return self._sequence
    +
    +    def append(self, operation: Operation) -> WalRecord:
    +        self._ensure_open()
    +        sequence = self._sequence + 1
    +        kind, payload = _encode_operation(operation)
    +        self._stream.write(encode_frame(sequence, kind, payload))
    +        if self._durability is Durability.ALWAYS:
    +            os.fsync(self._stream.fileno())
    +        self._sequence = sequence
    +        return WalRecord(sequence, operation)
    +
    +    def replay(self, *, after_sequence: int = 0) -> tuple[WalRecord, ...]:
    +        self._ensure_open()
    +        return tuple(
    +            WalRecord(frame.sequence, _decode_operation(frame))
    +            for frame in scan_frames(self._active_path, repair_tail=False)
    +            if frame.sequence > after_sequence
    +        )
    +
    +    def flush(self) -> None:
    +        self._ensure_open()
    +        os.fsync(self._stream.fileno())
    +
    +    def close(self) -> None:
    +        if self._closed:
    +            return
    +        self._stream.close()
    +        self._closed = True
    +
    +    def _ensure_open(self) -> None:
    +        if self._closed:
    +            raise ClosedResourceError("WAL is closed")
    +
    +
    +def _encode_operation(operation: Operation) -> tuple[int, bytes]:
    +    if isinstance(operation, UpsertOperation):
    +        value = {
    +            "points": [
    +                {
    +                    "id": _encode_id(point.id),
    +                    "vector": list(point.vector),
    +                    "payload": thaw_json(point.payload),
    +                }
    +                for point in operation.points
    +            ]
    +        }
    +        kind = 1
    +    else:
    +        value = {"point_ids": [_encode_id(point_id) for point_id in operation.point_ids]}
    +        kind = 2
    +    payload = json.dumps(
    +        value,
    +        ensure_ascii=False,
    +        allow_nan=False,
    +        sort_keys=True,
    +        separators=(",", ":"),
    +    ).encode("utf-8")
    +    return kind, payload
    +
    +
    +def _decode_operation(frame: DecodedFrame) -> Operation:
    +    try:
    +        value = json.loads(frame.payload)
    +        if frame.kind == 1:
    +            return UpsertOperation(
    +                tuple(
    +                    Point(
    +                        _decode_id(point["id"]),
    +                        tuple(point["vector"]),
    +                        point["payload"],
    +                    )
    +                    for point in value["points"]
    +                )
    +            )
    +        if frame.kind == 2:
    +            return DeleteOperation(
    +                tuple(_decode_id(point_id) for point_id in value["point_ids"])
    +            )
    +    except (KeyError, TypeError, ValueError, UnicodeDecodeError) as error:
    +        raise CorruptionError(f"invalid WAL operation at sequence {frame.sequence}") from error
    +    raise CorruptionError(f"unknown WAL operation kind {frame.kind}")
    +
    +
    +def _encode_id(value: object) -> dict[str, object]:
    +    point_id = canonicalize_point_id(value)
    +    if isinstance(point_id, int):
    +        return {"kind": "int", "value": point_id}
    +    return {"kind": "uuid", "value": str(point_id)}
    +
    +
    +def _decode_id(value: object) -> PointId:
    +    if not isinstance(value, dict):
    +        raise ValueError("point id encoding must be an object")
    +    if value.get("kind") == "int":
    +        return canonicalize_point_id(value.get("value"))
    +    if value.get("kind") == "uuid":
    +        return UUID(str(value.get("value")))
    +    raise ValueError("unknown point id encoding")
    +
    +
    +def _validate_sequences(frames: tuple[DecodedFrame, ...]) -> None:
    +    expected = 1
    +    for frame in frames:
    +        if frame.sequence != expected:
    +            raise CorruptionError(
    +                f"WAL sequence mismatch: expected {expected}, got {frame.sequence}"
    +            )
    +        expected += 1
    +
    ```

**是什么，为什么现在需要**

核心机制是分帧预写日志。已确认操作需要有序、带校验和的 Frame，使截断或尾部损坏后仍能恢复有效前缀。

**在运行时做什么**

Mutation 只有完整 Frame 持久后才能发布，恢复绝不跳过损坏去虚构后续历史。

**关键语句理解**

真正要守住的边界是：Mutation 只有完整 Frame 持久后才能发布，恢复绝不跳过损坏去虚构后续历史。

#### 包、Fixture 与工程支撑

保持包导出、测试语料、依赖与运行环境可复现。

??? note "支撑文件差异（1 个文件）"
    **`src/miniqdrant/persistence/__init__.py`**

    ```diff
    diff --git a/src/miniqdrant/persistence/__init__.py b/src/miniqdrant/persistence/__init__.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..a7e620c7be69e5671aa70e72f14fa064c3555d1b
    --- /dev/null
    +++ b/src/miniqdrant/persistence/__init__.py
    @@ -0,0 +1,18 @@
    +from miniqdrant.persistence.wal import (
    +    DeleteOperation,
    +    Durability,
    +    Operation,
    +    UpsertOperation,
    +    Wal,
    +    WalRecord,
    +)
    +
    +__all__ = [
    +    "DeleteOperation",
    +    "Durability",
    +    "Operation",
    +    "UpsertOperation",
    +    "Wal",
    +    "WalRecord",
    +]
    +
    ```


### 验证证据

运行 `uv run pytest -q $(cat journey/stages/09-framed-wal/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：Mutation 只有完整 Frame 持久后才能发布，恢复绝不跳过损坏去虚构后续历史。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 3 章](https://github.com/system-in-miniature/mini-qdrant/blob/main/docs/zh/tutorial/03-wal-manifest.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-qdrant/blob/main/journey/stages/09-framed-wal/stage.patch)
