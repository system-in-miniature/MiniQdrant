from __future__ import annotations

from miniqdrant.config import OptimizerConfig
from miniqdrant.optimizer.policy import (
    OptimizationKind,
    SegmentCandidate,
    choose_optimization,
)


def test_vacuum_has_priority_over_merge_and_indexing() -> None:
    plan = choose_optimization(
        (
            SegmentCandidate("large", live_points=100, deleted_points=0, indexed=False),
            SegmentCandidate("stale", live_points=7, deleted_points=3, indexed=False),
        ),
        OptimizerConfig(
            indexing_threshold_points=50,
            target_segment_count=1,
            deleted_ratio_threshold=0.2,
        ),
    )

    assert plan.kind is OptimizationKind.VACUUM
    assert plan.segment_ids == ("stale",)


def test_merge_selects_the_two_smallest_segments_deterministically() -> None:
    plan = choose_optimization(
        (
            SegmentCandidate("c", live_points=3, deleted_points=0, indexed=True),
            SegmentCandidate("b", live_points=1, deleted_points=0, indexed=True),
            SegmentCandidate("a", live_points=1, deleted_points=0, indexed=True),
        ),
        OptimizerConfig(target_segment_count=2),
    )

    assert plan.kind is OptimizationKind.MERGE
    assert plan.segment_ids == ("a", "b")


def test_large_plain_segment_is_selected_for_indexing() -> None:
    plan = choose_optimization(
        (SegmentCandidate("plain", live_points=10, deleted_points=0, indexed=False),),
        OptimizerConfig(indexing_threshold_points=10),
    )

    assert plan.kind is OptimizationKind.INDEX
    assert plan.segment_ids == ("plain",)
