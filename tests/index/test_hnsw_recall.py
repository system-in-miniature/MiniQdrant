from __future__ import annotations

import random

from miniqdrant.config import CollectionConfig, Distance, HnswConfig
from miniqdrant.index.hnsw import HnswIndex
from miniqdrant.index.plain import PlainVectorIndex
from miniqdrant.models import Point, normalize_cosine, validate_point


def test_hnsw_recall_reaches_required_floor() -> None:
    randomizer = random.Random(17)
    config = CollectionConfig(dimension=8, distance=Distance.COSINE)
    points = tuple(
        validate_point(
            Point(
                point_id,
                tuple(randomizer.uniform(-1.0, 1.0) for _ in range(config.dimension)),
                {},
            ),
            config,
        )
        for point_id in range(200)
    )
    exact = PlainVectorIndex(config.distance, points)
    approximate = HnswIndex.build(
        points,
        distance=config.distance,
        config=HnswConfig(m=12, ef_construct=64, ef_search=64, seed=19),
    )
    recalls = []

    for _ in range(20):
        query = normalize_cosine(
            tuple(randomizer.uniform(-1.0, 1.0) for _ in range(config.dimension))
        )
        expected = {item.point_id for item in exact.search(query, limit=10)}
        actual = {
            item.point_id
            for item in approximate.search(query, limit=10, ef_search=64).candidates
        }
        recalls.append(len(actual.intersection(expected)) / len(expected))

    assert sum(recalls) / len(recalls) >= 0.90

