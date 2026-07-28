from __future__ import annotations

from uuid import UUID

from miniqdrant.models import Point
from miniqdrant.persistence.wal import (
    DeleteOperation,
    Durability,
    UpsertOperation,
    Wal,
)


def test_wal_round_trip_is_binary_safe(tmp_path) -> None:
    wal = Wal.create(tmp_path / "wal", durability=Durability.ALWAYS)
    operation = UpsertOperation(
        (
            Point(1, (1.0, 2.0), {"text": "雪", "raw": "a\u0000b"}),
            Point(UUID(int=2), (3.0, 4.0), {"nested": [1, True, None]}),
        )
    )

    record = wal.append(operation)
    wal.close()
    reopened = Wal.open(tmp_path / "wal", durability=Durability.ALWAYS)

    assert record.sequence == 1
    assert list(reopened.replay()) == [record]


def test_delete_operation_round_trip(tmp_path) -> None:
    wal = Wal.create(tmp_path / "wal", durability=Durability.MANUAL)

    first = wal.append(DeleteOperation((1, UUID(int=4))))
    wal.flush()
    wal.close()

    assert list(Wal.open(tmp_path / "wal").replay()) == [first]


def test_sequences_continue_after_reopen(tmp_path) -> None:
    wal = Wal.create(tmp_path / "wal")
    wal.append(DeleteOperation((1,)))
    wal.close()

    reopened = Wal.open(tmp_path / "wal")

    assert reopened.append(DeleteOperation((2,))).sequence == 2

