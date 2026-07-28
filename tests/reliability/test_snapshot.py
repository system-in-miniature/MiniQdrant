from __future__ import annotations

from miniqdrant import Database, Distance, Point, SearchRequest


def test_snapshot_restores_searchable_collection(tmp_path) -> None:
    live_path = tmp_path / "live"
    collection = Database.open(live_path).create_collection(
        "items",
        dimension=2,
        distance=Distance.DOT,
    )
    collection.upsert(
        [
            Point(1, (1.0, 0.0), {"name": "one"}),
            Point(2, (0.0, 1.0), {"name": "two"}),
        ]
    )
    collection.optimize()
    expected = collection.search(SearchRequest((1.0, 0.0), 2))

    snapshot = collection.create_snapshot(tmp_path / "backups" / "sp-1")
    Database.restore_collection(snapshot, tmp_path / "restored", "items")
    restored = Database.open(tmp_path / "restored").collection("items")

    assert restored.search(SearchRequest((1.0, 0.0), 2)) == expected
    assert restored.retrieve([1, 2]) == collection.retrieve([1, 2])
