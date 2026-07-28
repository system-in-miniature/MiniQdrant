from __future__ import annotations

from miniqdrant.config import CollectionConfig, Distance
from miniqdrant.filters import Filter, Match
from miniqdrant.index.plain import PlainVectorIndex
from miniqdrant.models import Point, validate_point


def test_plain_index_returns_exact_filtered_topk() -> None:
    config = CollectionConfig(dimension=2, distance=Distance.DOT)
    points = [
        validate_point(Point(1, (1.0, 0.0), {"kind": "book"}), config),
        validate_point(Point(2, (0.9, 0.1), {"kind": "movie"}), config),
        validate_point(Point(3, (0.8, 0.2), {"kind": "book"}), config),
    ]
    index = PlainVectorIndex(config.distance, points)

    candidates = index.search(
        query=(1.0, 0.0),
        limit=2,
        filter_=Filter(must=(Match("kind", "book"),)),
    )

    assert [(item.point_id, item.score) for item in candidates] == [
        (1, 1.0),
        (3, 0.8),
    ]


def test_plain_index_reports_visited_points() -> None:
    config = CollectionConfig(dimension=2, distance=Distance.DOT)
    points = [
        validate_point(Point(1, (1.0, 0.0), {}), config),
        validate_point(Point(2, (0.0, 1.0), {}), config),
    ]
    index = PlainVectorIndex(config.distance, points)

    result = index.search_with_stats(query=(1.0, 0.0), limit=1)

    assert result.visited_count == 2
    assert result.candidates[0].point_id == 1

