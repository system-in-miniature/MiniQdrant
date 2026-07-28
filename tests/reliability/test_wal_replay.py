from __future__ import annotations

from miniqdrant.models import Point
from miniqdrant.persistence.wal import DeleteOperation, UpsertOperation, Wal


def test_replay_can_start_after_manifest_boundary(tmp_path) -> None:
    wal = Wal.create(tmp_path / "wal")
    wal.append(UpsertOperation((Point(1, (1.0,), {}),)))
    wal.append(DeleteOperation((1,)))
    third = wal.append(UpsertOperation((Point(1, (2.0,), {}),)))

    assert list(wal.replay(after_sequence=2)) == [third]

