from __future__ import annotations

from miniqdrant import Database, Distance, Filter, Match, Point, SearchRequest
from miniqdrant.filters.index import PayloadSchema


def test_indexed_and_unindexed_exact_search_return_same_hits(tmp_path) -> None:
    database = Database.open(tmp_path)
    plain = database.create_collection("plain", dimension=2, distance=Distance.DOT)
    indexed = database.create_collection("indexed", dimension=2, distance=Distance.DOT)
    points = [
        Point(1, (1.0, 0.0), {"kind": "book"}),
        Point(2, (0.9, 0.1), {"kind": "movie"}),
        Point(3, (0.8, 0.2), {"kind": "book"}),
    ]
    plain.upsert(points)
    indexed.upsert(points)
    indexed.create_payload_index("kind", PayloadSchema.KEYWORD)
    request = SearchRequest(
        (1.0, 0.0),
        10,
        filter=Filter(must=(Match("kind", "book"),)),
        exact=True,
    )

    assert indexed.search(request).hits == plain.search(request).hits

