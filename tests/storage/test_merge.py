from __future__ import annotations

from miniqdrant import Database, Distance, Point


def test_merge_reduces_segments_and_preserves_latest_versions(tmp_path) -> None:
    collection = Database.open(tmp_path).create_collection(
        "items",
        dimension=2,
        distance=Distance.DOT,
    )
    collection.upsert([Point(1, (1.0, 0.0), {"value": "old"})])
    collection.flush()
    collection.upsert([Point(1, (0.0, 1.0), {"value": "new"})])
    collection.upsert([Point(2, (1.0, 1.0), {})])
    collection.flush()

    assert collection.segment_statistics().segment_count == 2

    collection.merge()

    statistics = collection.segment_statistics()
    assert statistics.segment_count == 1
    assert statistics.live_points == 2
    assert collection.retrieve([1])[0].payload["value"] == "new"

