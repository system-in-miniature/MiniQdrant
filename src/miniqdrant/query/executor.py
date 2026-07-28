from __future__ import annotations

from miniqdrant.filters import matches_filter
from miniqdrant.filters.index import CandidateSet
from miniqdrant.index.quantization import ScalarQuantizedIndex
from miniqdrant.models import Vector
from miniqdrant.query.planner import QueryPlanner, SearchPlan, SegmentFacts, Strategy
from miniqdrant.segment.base import ScoredCandidate


def execute_quantized_rescore(
    index: ScalarQuantizedIndex,
    query: Vector,
    candidates: CandidateSet,
    *,
    limit: int,
    oversampling: int,
) -> tuple[tuple[ScoredCandidate, ...], int]:
    return index.search(
        query,
        limit=limit,
        oversampling=oversampling,
        allowed_ids=candidates.ids,
        predicate=(
            None
            if candidates.residual is None
            else lambda point: matches_filter(
                point.id,
                point.payload,
                candidates.residual,
            )
        ),
    )


__all__ = [
    "QueryPlanner",
    "SearchPlan",
    "SegmentFacts",
    "Strategy",
    "execute_quantized_rescore",
]
