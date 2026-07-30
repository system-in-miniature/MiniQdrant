"""Compare the work and output of MiniQdrant's four teaching search plans.

Collection-level ``SearchResult.plan`` exposes these same strategy names but
does not retain visit counts. This lab calls the per-segment search boundary so
it can show both the plan and its strategy-specific ``visited_count``.
"""

from __future__ import annotations

import math

from miniqdrant.config import (
    CollectionConfig,
    Distance,
    HnswConfig,
    OptimizerConfig,
    ScalarQuantizationConfig,
)
from miniqdrant.filters import Filter, Match
from miniqdrant.filters.index import PayloadSchema
from miniqdrant.models import Point, StoredPoint, validate_point
from miniqdrant.segment import ImmutableSegment, SegmentSearchRequest


def run_plan_comparison_lab(*, points: int = 64) -> tuple[dict[str, object], ...]:
    """Run one query through exact, HNSW, filtered-HNSW, and quantized plans."""
    if points < 8:
        raise ValueError("plan comparison requires at least 8 points")

    base_config = CollectionConfig(
        dimension=2,
        distance=Distance.DOT,
        hnsw=HnswConfig(m=8, ef_construct=32, ef_search=16, seed=19),
        optimizer=OptimizerConfig(indexing_threshold_points=1),
    )
    records = _circle_records(points, base_config)
    indexed = ImmutableSegment.build(
        base_config,
        records,
        payload_schemas={"cohort": PayloadSchema.KEYWORD},
        indexed=True,
    )
    quantized_config = CollectionConfig(
        dimension=base_config.dimension,
        distance=base_config.distance,
        hnsw=base_config.hnsw,
        optimizer=base_config.optimizer,
        quantization=ScalarQuantizationConfig(oversampling=4),
    )
    quantized = ImmutableSegment.build(
        quantized_config,
        records,
        payload_schemas={"cohort": PayloadSchema.KEYWORD},
        indexed=True,
    )

    query = (1.0, 0.0)
    requests = (
        ("exact", indexed, SegmentSearchRequest(query, 5, exact=True)),
        ("hnsw", indexed, SegmentSearchRequest(query, 5)),
        (
            "filtered",
            indexed,
            SegmentSearchRequest(
                query,
                5,
                filter=Filter(must=(Match("cohort", "even"),)),
            ),
        ),
        ("quantized", quantized, SegmentSearchRequest(query, 5)),
    )
    rows: list[dict[str, object]] = []
    for label, segment, request in requests:
        result = segment.search(request)
        rows.append(
            {
                "label": label,
                "plan": result.strategy,
                "ids": tuple(candidate.point_id for candidate in result.candidates),
                "scores": tuple(
                    round(candidate.score, 6) for candidate in result.candidates
                ),
                "visited_count": result.visited_count,
            }
        )
    return tuple(rows)


def _circle_records(
    count: int,
    config: CollectionConfig,
) -> tuple[StoredPoint, ...]:
    records = []
    for point_id in range(count):
        angle = 2.0 * math.pi * point_id / count
        record = validate_point(
            Point(
                point_id,
                (math.cos(angle), math.sin(angle)),
                {"cohort": "even" if point_id % 2 == 0 else "odd"},
            ),
            config,
        )
        records.append(
            StoredPoint(
                record.id,
                record.vector,
                record.payload,
                version=1,
            )
        )
    return tuple(records)


def main() -> None:
    print("Same query: vector=(1.0, 0.0), limit=5")
    print(
        "`visited_count` is the plan-specific work counter: scored eligible "
        "vectors or unique graph nodes."
    )
    for row in run_plan_comparison_lab():
        print(
            f"{row['label']:>9} | plan={row['plan']:<24} "
            f"| visited={row['visited_count']:>3} | ids={row['ids']}"
        )
    print()
    print("Interpretation:")
    print("- exact visits every eligible vector; HNSW follows the graph.")
    print("- filtered-HNSW traverses first and filters an oversampled candidate set.")
    print("- the quantized plan scans decoded int8 codes, then float-rescores candidates.")
    print("- plan names describe planner branches; see DIFFERENCES_FROM_QDRANT.md.")


if __name__ == "__main__":
    main()
