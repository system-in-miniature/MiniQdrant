from __future__ import annotations

from miniqdrant.config import CollectionConfig, Distance
from miniqdrant.filters import Filter, Match, Range, matches_filter
from miniqdrant.filters.index import PayloadIndexSet, PayloadSchema
from miniqdrant.models import Point, validate_point


def points():
    config = CollectionConfig(dimension=2, distance=Distance.DOT)
    return tuple(
        validate_point(point, config)
        for point in (
            Point(1, (1, 0), {"kind": "book", "price": 10.0}),
            Point(2, (0, 1), {"kind": "movie", "price": 20.0}),
            Point(3, (1, 1), {"kind": "book", "price": 30.0}),
        )
    )


def test_payload_index_candidates_equal_scan() -> None:
    stored = points()
    indexes = PayloadIndexSet(record.id for record in stored)
    indexes.create("kind", PayloadSchema.KEYWORD, stored)
    indexes.create("price", PayloadSchema.FLOAT, stored)
    condition = Filter(
        must=(Match("kind", "book"), Range("price", lte=20.0)),
    )

    indexed = indexes.candidates(condition)
    scanned = {
        point.id
        for point in stored
        if matches_filter(point.id, point.payload, condition)
    }

    assert indexed.exact
    assert indexed.ids == scanned == {1}
    assert indexed.estimate.minimum == 1
    assert indexed.estimate.maximum == 1


def test_unindexed_condition_is_retained_as_residual() -> None:
    stored = points()
    indexes = PayloadIndexSet(record.id for record in stored)
    indexes.create("kind", PayloadSchema.KEYWORD, stored)
    condition = Filter(
        must=(Match("kind", "book"), Range("price", lte=20.0)),
    )

    candidates = indexes.candidates(condition)

    assert not candidates.exact
    assert candidates.ids == {1, 3}
    assert candidates.residual is condition
    assert candidates.estimate.maximum == 2


def test_index_update_removes_old_value() -> None:
    stored = points()
    indexes = PayloadIndexSet(record.id for record in stored)
    indexes.create("kind", PayloadSchema.KEYWORD, stored)
    replacement = validate_point(
        Point(1, (1, 0), {"kind": "movie", "price": 10.0}),
        CollectionConfig(dimension=2, distance=Distance.DOT),
    )

    indexes.upsert(replacement)

    books = indexes.candidates(Filter(must=(Match("kind", "book"),)))
    assert books.ids == {3}

