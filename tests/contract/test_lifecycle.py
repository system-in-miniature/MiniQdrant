from __future__ import annotations

import pytest

from miniqdrant import (
    ClosedResourceError,
    Database,
    Distance,
    Point,
    SearchRequest,
)


def test_close_is_idempotent_and_rejects_new_collection_work(tmp_path) -> None:
    collection = Database.open(tmp_path).create_collection(
        "items",
        dimension=2,
        distance=Distance.DOT,
    )
    collection.close()
    collection.close()

    with pytest.raises(ClosedResourceError):
        collection.upsert([Point(1, (1.0, 0.0), {})])
    with pytest.raises(ClosedResourceError):
        collection.search(SearchRequest((1.0, 0.0), 1))


def test_database_close_closes_owned_collections(tmp_path) -> None:
    database = Database.open(tmp_path)
    collection = database.create_collection(
        "items",
        dimension=2,
        distance=Distance.DOT,
    )

    database.close()
    database.close()

    with pytest.raises(ClosedResourceError):
        database.collection("items")
    with pytest.raises(ClosedResourceError):
        collection.retrieve([1])
