from __future__ import annotations

from uuid import UUID

import pytest

from miniqdrant.topk import TopK


def test_topk_keeps_only_best_candidates() -> None:
    collector = TopK(2)

    collector.offer(1, 0.5)
    collector.offer(2, 0.9)
    collector.offer(3, 0.7)

    assert [(item.point_id, item.score) for item in collector.results()] == [
        (2, 0.9),
        (3, 0.7),
    ]
    assert len(collector) == 2


def test_topk_breaks_equal_scores_by_canonical_id() -> None:
    collector = TopK(2)

    collector.offer(2, 1.0)
    collector.offer(1, 1.0)
    collector.offer(3, 1.0)

    assert [candidate.point_id for candidate in collector.results()] == [1, 2]


def test_integer_ids_sort_before_uuid_ids_on_equal_score() -> None:
    collector = TopK(2)
    first_uuid = UUID(int=0)

    collector.offer(first_uuid, 1.0)
    collector.offer(42, 1.0)

    assert [candidate.point_id for candidate in collector.results()] == [42, first_uuid]


def test_topk_rejects_invalid_capacity_and_non_finite_score() -> None:
    with pytest.raises(ValueError, match="positive"):
        TopK(0)

    collector = TopK(1)
    with pytest.raises(ValueError, match="finite"):
        collector.offer(1, float("nan"))

