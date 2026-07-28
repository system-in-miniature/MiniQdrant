from __future__ import annotations

import os

import pytest

from miniqdrant.errors import CorruptionError
from miniqdrant.persistence.wal import DeleteOperation, Wal


def populated_wal(tmp_path) -> Wal:
    wal = Wal.create(tmp_path / "wal")
    wal.append(DeleteOperation((1,)))
    wal.append(DeleteOperation((2,)))
    wal.flush()
    return wal


def test_incomplete_active_tail_is_truncated(tmp_path) -> None:
    wal = populated_wal(tmp_path)
    original_size = wal.active_path.stat().st_size
    wal.close()
    with (tmp_path / "wal" / "00000000000000000001.wal").open("ab") as stream:
        stream.write(b"\x00\x00\x00")

    reopened = Wal.open(tmp_path / "wal")

    assert [item.sequence for item in reopened.replay()] == [1, 2]
    assert reopened.active_path.stat().st_size == original_size


def test_corrupt_last_frame_is_truncated(tmp_path) -> None:
    wal = populated_wal(tmp_path)
    path = wal.active_path
    wal.close()
    with path.open("r+b") as stream:
        stream.seek(-1, os.SEEK_END)
        byte = stream.read(1)
        stream.seek(-1, os.SEEK_END)
        stream.write(bytes([byte[0] ^ 0xFF]))

    reopened = Wal.open(tmp_path / "wal")

    assert [item.sequence for item in reopened.replay()] == [1]


def test_corruption_before_active_tail_is_fatal(tmp_path) -> None:
    wal = populated_wal(tmp_path)
    path = wal.active_path
    wal.close()
    with path.open("r+b") as stream:
        stream.seek(20)
        byte = stream.read(1)
        stream.seek(20)
        stream.write(bytes([byte[0] ^ 0xFF]))

    with pytest.raises(CorruptionError):
        Wal.open(tmp_path / "wal")

