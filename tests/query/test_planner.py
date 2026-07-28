from __future__ import annotations

import pytest

from miniqdrant.filters.cardinality import CardinalityEstimate
from miniqdrant.query.planner import QueryPlanner, SegmentFacts, Strategy


@pytest.mark.parametrize(
    ("facts", "expected"),
    [
        (SegmentFacts(total_points=10), Strategy.EXACT_FULL_SCAN),
        (
            SegmentFacts(
                total_points=10_000,
                filtered=CardinalityEstimate.exact_count(5),
            ),
            Strategy.FILTER_THEN_EXACT,
        ),
        (
            SegmentFacts(
                total_points=10_000,
                filtered=CardinalityEstimate(0, 4_000, 8_000, False),
            ),
            Strategy.FILTERED_HNSW,
        ),
        (SegmentFacts(total_points=10_000), Strategy.HNSW),
        (
            SegmentFacts(total_points=10_000, has_quantization=True),
            Strategy.QUANTIZED_HNSW_RESCORE,
        ),
        (
            SegmentFacts(total_points=10_000, exact_requested=True),
            Strategy.EXACT_FULL_SCAN,
        ),
    ],
)
def test_planner_boundaries(facts, expected) -> None:
    plan = QueryPlanner(plain_threshold=100, filter_scan_threshold=100).choose(facts)
    assert plan.strategy is expected


def test_plan_is_inspectable() -> None:
    plan = QueryPlanner(plain_threshold=100, filter_scan_threshold=100).choose(
        SegmentFacts(total_points=10)
    )

    assert plan.reason == "segment below plain-scan threshold"
    assert plan.total_points == 10
