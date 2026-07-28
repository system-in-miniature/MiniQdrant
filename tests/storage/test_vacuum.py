from __future__ import annotations

from miniqdrant import Database, Distance, Point


def test_vacuum_drops_obsolete_images_and_tombstones(tmp_path) -> None:
    collection = Database.open(tmp_path).create_collection(
        "items",
        dimension=2,
        distance=Distance.DOT,
    )
    collection.upsert(
        [
            Point(1, (1.0, 0.0), {}),
            Point(2, (0.0, 1.0), {}),
        ]
    )
    collection.flush()
    collection.delete([1])
    collection.flush()

    assert collection.segment_statistics().deleted_points == 1

    collection.vacuum()

    statistics = collection.segment_statistics()
    assert statistics.live_points == 1
    assert statistics.deleted_points == 0
    assert collection.retrieve([1]) == ()

