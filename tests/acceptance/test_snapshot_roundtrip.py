from __future__ import annotations

from miniqdrant import Database, Distance, Point, SearchRequest


def test_snapshot_roundtrip_survives_source_removal(tmp_path) -> None:
    source_path = tmp_path / "source"
    source_database = Database.open(source_path)
    collection = source_database.create_collection(
        "vectors",
        dimension=3,
        distance=Distance.COSINE,
    )
    collection.upsert(
        [
            Point(7, (1.0, 0.0, 0.0), {"tenant": "a"}),
            Point(8, (0.0, 1.0, 0.0), {"tenant": "b"}),
        ]
    )
    snapshot = collection.create_snapshot(tmp_path / "snapshots" / "portable")
    source_database.close()

    Database.restore_collection(snapshot, tmp_path / "new-db", "restored")
    restored = Database.open(tmp_path / "new-db").collection("restored")

    assert [hit.id for hit in restored.search(SearchRequest((1.0, 0.0, 0.0), 2)).hits] == [
        7,
        8,
    ]
