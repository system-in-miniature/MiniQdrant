from __future__ import annotations

from miniqdrant.config import CollectionConfig, Distance, HnswConfig
from miniqdrant.index.hnsw import HnswIndex
from miniqdrant.models import Point, validate_point


def build_index() -> HnswIndex:
    config = CollectionConfig(dimension=2, distance=Distance.DOT)
    points = tuple(
        validate_point(Point(index, (float(index), 1.0), {}), config)
        for index in range(1, 21)
    )
    return HnswIndex.build(
        points,
        distance=Distance.DOT,
        config=HnswConfig(m=6, ef_construct=24, ef_search=12, seed=3),
    )


def test_hnsw_returns_best_candidates_in_score_order() -> None:
    result = build_index().search((1.0, 0.0), limit=3, ef_search=16)

    assert [candidate.point_id for candidate in result.candidates] == [20, 19, 18]
    assert result.visited_count >= 3


def test_hnsw_never_returns_deleted_or_disallowed_point() -> None:
    index = build_index()
    index.mark_deleted(20)

    result = index.search(
        (1.0, 0.0),
        limit=10,
        ef_search=16,
        allowed_ids={18, 20},
    )

    assert [candidate.point_id for candidate in result.candidates] == [18]


def test_ef_search_is_raised_to_limit() -> None:
    result = build_index().search((1.0, 0.0), limit=8, ef_search=2)

    assert len(result.candidates) == 8

