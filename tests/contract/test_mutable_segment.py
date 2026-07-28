from __future__ import annotations

from miniqdrant.config import CollectionConfig, Distance
from miniqdrant.filters import Filter, Match
from miniqdrant.models import Point
from miniqdrant.segment import MutableSegment, SegmentSearchRequest


def config() -> CollectionConfig:
    return CollectionConfig(dimension=2, distance=Distance.DOT)


def test_exact_search_obeys_filter_and_topk() -> None:
    segment = MutableSegment(config())
    segment.apply_upsert(Point(1, (1.0, 0.0), {"kind": "book"}), version=1)
    segment.apply_upsert(Point(2, (0.9, 0.1), {"kind": "movie"}), version=2)
    segment.apply_upsert(Point(3, (0.8, 0.2), {"kind": "book"}), version=3)

    hits = segment.search(
        SegmentSearchRequest(
            vector=(1.0, 0.0),
            limit=1,
            filter=Filter(must=(Match("kind", "book"),)),
            exact=True,
        )
    )

    assert [(hit.point_id, hit.version) for hit in hits.candidates] == [(1, 1)]


def test_stale_version_cannot_resurrect_deleted_point() -> None:
    segment = MutableSegment(config())
    assert segment.apply_upsert(Point(1, (1.0, 0.0), {}), version=4)
    assert segment.apply_delete(1, version=5)

    assert not segment.apply_upsert(Point(1, (0.0, 1.0), {}), version=3)
    assert segment.get(1) is None
    assert segment.version_of(1) == 5


def test_equal_version_is_idempotently_ignored() -> None:
    segment = MutableSegment(config())

    assert segment.apply_upsert(Point(1, (1.0, 0.0), {"value": "first"}), version=7)
    assert not segment.apply_upsert(Point(1, (0.0, 1.0), {"value": "second"}), version=7)

    assert segment.get(1).payload["value"] == "first"


def test_delete_of_missing_point_creates_tombstone() -> None:
    segment = MutableSegment(config())

    assert segment.apply_delete(99, version=3)

    assert segment.get(99) is None
    assert segment.version_of(99) == 3
    assert segment.live_count == 0

