from __future__ import annotations

import pytest

from miniqdrant import (
    CollectionExistsError,
    CollectionNotFoundError,
    Database,
    Distance,
    Filter,
    Match,
    Point,
    SearchRequest,
)


def test_direct_exact_collection_loop(tmp_path) -> None:
    database = Database.open(tmp_path)
    collection = database.create_collection("products", dimension=2, distance="cosine")
    collection.upsert(
        [
            Point(1, (1.0, 0.0), {"category": "book"}),
            Point(2, (0.8, 0.2), {"category": "movie"}),
            Point(3, (0.7, 0.3), {"category": "book"}),
        ]
    )

    result = collection.search(
        SearchRequest(
            vector=(1.0, 0.0),
            limit=2,
            filter=Filter(must=(Match("category", "book"),)),
            exact=True,
        )
    )

    assert [hit.id for hit in result.hits] == [1, 3]
    assert all(hit.payload["category"] == "book" for hit in result.hits)


def test_database_collection_ownership(tmp_path) -> None:
    database = Database.open(tmp_path)
    created = database.create_collection("items", dimension=2, distance=Distance.DOT)

    assert database.collection("items") is created
    with pytest.raises(CollectionExistsError):
        database.create_collection("items", dimension=2, distance=Distance.DOT)

    database.drop_collection("items")

    with pytest.raises(CollectionNotFoundError):
        database.collection("items")

