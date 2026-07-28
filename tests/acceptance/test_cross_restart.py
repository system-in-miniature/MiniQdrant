from __future__ import annotations

from miniqdrant import Database, Distance, Filter, Match, Point, SearchRequest


def test_cross_restart_preserves_version_delete_filter_and_order(tmp_path) -> None:
    database = Database.open(tmp_path)
    collection = database.create_collection("items", dimension=2, distance=Distance.DOT)
    collection.create_payload_index("kind", "keyword")
    collection.upsert(
        [
            Point(1, (1.0, 0.0), {"kind": "book"}),
            Point(2, (0.9, 0.1), {"kind": "book"}),
        ]
    )
    collection.flush(indexed=True)
    collection.delete([1])
    collection.upsert([Point(2, (0.8, 0.2), {"kind": "book", "version": "new"})])
    database.close()

    reopened = Database.open(tmp_path).collection("items")
    result = reopened.search(
        SearchRequest(
            (1.0, 0.0),
            10,
            filter=Filter(must=(Match("kind", "book"),)),
            exact=True,
        )
    )

    assert [hit.id for hit in result.hits] == [2]
    assert result.hits[0].payload["version"] == "new"

