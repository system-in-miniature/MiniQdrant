from __future__ import annotations

import random

import pytest

from miniqdrant import (
    Database,
    Distance,
    OptimizerConfig,
    Point,
    ScalarQuantizationConfig,
    SearchRequest,
)
from miniqdrant.metrics import score


def test_quantized_candidates_are_rescored_with_original_vectors(tmp_path) -> None:
    collection = Database.open(tmp_path).create_collection(
        "items",
        dimension=2,
        distance=Distance.DOT,
        optimizer=OptimizerConfig(indexing_threshold_points=1),
        quantization=ScalarQuantizationConfig(oversampling=3),
    )
    collection.upsert(
        [
            Point(1, (0.91, 0.11), {}),
            Point(2, (0.89, 0.13), {}),
            Point(3, (0.20, 0.99), {}),
            Point(4, (-0.50, 0.40), {}),
        ]
    )
    collection.flush(indexed=True)
    query = (1.0, 0.0)

    result = collection.search(SearchRequest(query, limit=2))

    assert result.plan == ("quantized_hnsw_rescore",)
    assert [hit.id for hit in result.hits] == [1, 2]
    originals = {point.id: point.vector for point in collection.retrieve([1, 2])}
    assert [hit.score for hit in result.hits] == pytest.approx(
        [score(Distance.DOT, query, originals[hit.id]) for hit in result.hits]
    )


def test_exact_request_bypasses_quantized_candidate_scoring(tmp_path) -> None:
    collection = Database.open(tmp_path).create_collection(
        "items",
        dimension=2,
        distance=Distance.EUCLID,
        optimizer=OptimizerConfig(indexing_threshold_points=1),
        quantization=ScalarQuantizationConfig(),
    )
    collection.upsert(
        [Point(index, (float(index), float(index % 3)), {}) for index in range(12)]
    )
    collection.flush(indexed=True)
    query = (4.25, 1.0)

    approximate = collection.search(SearchRequest(query, limit=5))
    exact = collection.search(SearchRequest(query, limit=5, exact=True))

    assert approximate.hits == exact.hits
    assert approximate.plan == ("quantized_hnsw_rescore",)
    assert exact.plan == ("exact_full_scan",)


def test_quantized_oversampling_reaches_required_recall_floor(tmp_path) -> None:
    generator = random.Random(17)
    collection = Database.open(tmp_path).create_collection(
        "items",
        dimension=8,
        distance=Distance.DOT,
        optimizer=OptimizerConfig(indexing_threshold_points=1),
        quantization=ScalarQuantizationConfig(oversampling=4),
    )
    collection.upsert(
        [
            Point(
                point_id,
                tuple(generator.uniform(-1.0, 1.0) for _ in range(8)),
                {},
            )
            for point_id in range(200)
        ]
    )
    collection.flush(indexed=True)

    recalls = []
    for _ in range(10):
        query = tuple(generator.uniform(-1.0, 1.0) for _ in range(8))
        approximate = collection.search(SearchRequest(query, limit=10))
        exact = collection.search(SearchRequest(query, limit=10, exact=True))
        approximate_ids = {hit.id for hit in approximate.hits}
        exact_ids = {hit.id for hit in exact.hits}
        recalls.append(len(approximate_ids & exact_ids) / len(exact_ids))

    assert min(recalls) >= 0.95
