from __future__ import annotations

import pytest

from miniqdrant import (
    ClosedResourceError,
    Database,
    Distance,
    InvalidVectorError,
    Point,
    SearchRequest,
)


def test_invalid_batch_does_not_partially_apply(tmp_path) -> None:
    database = Database.open(tmp_path)
    collection = database.create_collection("items", dimension=2, distance=Distance.DOT)

    with pytest.raises(InvalidVectorError):
        collection.upsert(
            [
                Point(1, (1.0, 0.0), {}),
                Point(2, (1.0,), {}),
            ]
        )

    assert collection.count() == 0
    assert collection.retrieve([1, 2]) == ()


def test_payload_mutations_create_versioned_full_point_images(tmp_path) -> None:
    database = Database.open(tmp_path)
    collection = database.create_collection(
        "items",
        dimension=2,
        distance=Distance.DOT,
    )
    collection.upsert(
        [
            Point(1, (1.0, 0.0), {"a": 1, "remove": True}),
            Point(2, (0.0, 1.0), {"a": 2}),
        ]
    )

    collection.replace_payload([1], {"kind": "book", "remove": True})
    collection.merge_payload([1, 2], {"active": True})
    collection.delete_payload_keys([1], ["remove"])
    database.close()

    reopened = Database.open(tmp_path).collection("items")
    first, second = reopened.retrieve([1, 2])
    assert dict(first.payload) == {"active": True, "kind": "book"}
    assert dict(second.payload) == {"a": 2, "active": True}
    assert first.vector == (1.0, 0.0)
    assert second.vector == (0.0, 1.0)


def test_upsert_delete_retrieve_and_search(tmp_path) -> None:
    database = Database.open(tmp_path)
    collection = database.create_collection("items", dimension=2, distance=Distance.DOT)

    first_version = collection.upsert([Point(1, (1.0, 0.0), {"kind": "book"})])

    assert first_version == 1
    assert collection.retrieve([1])[0].id == 1
    assert collection.search(SearchRequest((1.0, 0.0), 1)).hits[0].id == 1

    delete_version = collection.delete([1])

    assert delete_version == 2
    assert collection.retrieve([1]) == ()
    assert collection.search(SearchRequest((1.0, 0.0), 1)).hits == ()


def test_search_response_projection_and_threshold(tmp_path) -> None:
    collection = Database.open(tmp_path).create_collection(
        "items",
        dimension=2,
        distance=Distance.DOT,
    )
    collection.upsert([Point(1, (0.5, 0.0), {"kind": "book"})])

    omitted = collection.search(
        SearchRequest(
            (1.0, 0.0),
            1,
            score_threshold=0.4,
            with_payload=False,
            with_vector=True,
        )
    )
    excluded = collection.search(SearchRequest((1.0, 0.0), 1, score_threshold=0.6))

    assert omitted.hits[0].payload is None
    assert omitted.hits[0].vector == (0.5, 0.0)
    assert excluded.hits == ()


def test_collection_close_is_idempotent_and_rejects_new_work(tmp_path) -> None:
    collection = Database.open(tmp_path).create_collection(
        "items",
        dimension=2,
        distance=Distance.DOT,
    )

    collection.close()
    collection.close()

    with pytest.raises(ClosedResourceError):
        collection.upsert([Point(1, (1.0, 0.0), {})])
