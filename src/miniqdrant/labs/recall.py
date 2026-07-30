"""Mechanism lab: compare HNSW candidates with exact segment search.

This experiment deliberately calls ``ImmutableSegment.search`` and
``SegmentSearchRequest`` directly so approximate and exact execution can be
compared at the internal per-segment mechanism boundary.
"""

from __future__ import annotations

import random

from miniqdrant.config import CollectionConfig, Distance, HnswConfig, OptimizerConfig
from miniqdrant.models import Point, validate_point
from miniqdrant.segment import ImmutableSegment, SegmentSearchRequest


def run_recall_lab(
    *,
    seed: int = 7,
    points: int = 200,
    queries: int = 10,
) -> dict[str, object]:
    generator = random.Random(seed)
    config = CollectionConfig(
        dimension=8,
        distance=Distance.DOT,
        hnsw=HnswConfig(m=8, ef_construct=40, ef_search=32, seed=seed),
        optimizer=OptimizerConfig(indexing_threshold_points=1),
    )
    records = tuple(
        validate_point(
            Point(
                point_id,
                tuple(generator.uniform(-1.0, 1.0) for _ in range(8)),
                {},
            ),
            config,
        )
        for point_id in range(points)
    )
    versioned = tuple(
        type(record)(
            record.id,
            record.vector,
            record.payload,
            version=1,
            deleted=False,
        )
        for record in records
    )
    segment = ImmutableSegment.build(config, versioned, indexed=True)
    recalls = []
    for _ in range(queries):
        query = tuple(generator.uniform(-1.0, 1.0) for _ in range(8))
        approximate = segment.search(SegmentSearchRequest(query, 5))
        exact = segment.search(SegmentSearchRequest(query, 5, exact=True))
        approximate_ids = {candidate.point_id for candidate in approximate.candidates}
        exact_ids = {candidate.point_id for candidate in exact.candidates}
        recalls.append(len(approximate_ids & exact_ids) / max(1, len(exact_ids)))
    return {
        "points": points,
        "queries": queries,
        "recall_at_5": sum(recalls) / max(1, len(recalls)),
        "seed": seed,
    }


def main() -> None:
    result = run_recall_lab(seed=11, points=80, queries=5)

    print(
        "Recall lab: "
        f"seed={result['seed']}, points={result['points']}, queries={result['queries']}"
    )
    print(f"Mean recall@5: {result['recall_at_5']:.3f}")
    print()
    print("Interpretation:")
    print("- exact search supplies the top-5 reference set for each query.")
    print("- recall@5 is the fraction of those ids also returned by internal HNSW search.")
    print("- the fixed seed makes this mechanism experiment reproducible.")


if __name__ == "__main__":
    main()
