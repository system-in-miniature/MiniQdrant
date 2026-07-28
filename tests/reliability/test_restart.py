from __future__ import annotations

from miniqdrant import Database, Distance, Point, SearchRequest
from miniqdrant.persistence import Durability


def test_acknowledged_unflushed_upsert_survives_restart(tmp_path) -> None:
    database = Database.open(tmp_path, durability=Durability.ALWAYS)
    collection = database.create_collection("items", dimension=2, distance=Distance.DOT)
    collection.upsert([Point(1, (1.0, 0.0), {"state": "wal-only"})])

    database.simulate_process_loss()
    reopened = Database.open(tmp_path, durability=Durability.ALWAYS)

    assert reopened.collection("items").retrieve([1])[0].payload["state"] == "wal-only"


def test_flushed_segments_and_later_wal_suffix_restore_together(tmp_path) -> None:
    database = Database.open(tmp_path)
    collection = database.create_collection("items", dimension=2, distance=Distance.DOT)
    collection.upsert([Point(1, (1.0, 0.0), {"state": "segment"})])
    collection.flush(indexed=True)
    collection.upsert([Point(2, (0.0, 1.0), {"state": "wal"})])
    database.simulate_process_loss()

    reopened = Database.open(tmp_path).collection("items")

    assert [point.id for point in reopened.retrieve([1, 2])] == [1, 2]
    assert reopened.search(SearchRequest((1.0, 0.0), 2, exact=True)).hits[0].id == 1


def test_payload_index_schema_survives_restart(tmp_path) -> None:
    database = Database.open(tmp_path)
    collection = database.create_collection("items", dimension=2, distance=Distance.DOT)
    collection.create_payload_index("kind", "keyword")
    collection.upsert([Point(1, (1.0, 0.0), {"kind": "book"})])
    database.close()

    reopened = Database.open(tmp_path).collection("items")

    assert reopened.payload_index_schemas == {"kind": "keyword"}

