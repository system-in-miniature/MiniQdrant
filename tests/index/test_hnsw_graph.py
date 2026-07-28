from __future__ import annotations

import math

from miniqdrant.config import CollectionConfig, Distance, HnswConfig
from miniqdrant.index.hnsw import HnswIndex
from miniqdrant.models import Point, validate_point


def circle_points(count: int = 40):
    config = CollectionConfig(dimension=2, distance=Distance.COSINE)
    return tuple(
        validate_point(
            Point(
                index,
                (
                    math.cos(2 * math.pi * index / count),
                    math.sin(2 * math.pi * index / count),
                ),
                {},
            ),
            config,
        )
        for index in range(count)
    )


def test_same_seed_builds_same_graph() -> None:
    points = circle_points()
    config = HnswConfig(m=6, ef_construct=32, ef_search=16, seed=7)

    first = HnswIndex.build(points, distance=Distance.COSINE, config=config)
    second = HnswIndex.build(reversed(points), distance=Distance.COSINE, config=config)

    assert first.export_graph() == second.export_graph()


def test_graph_respects_level_and_degree_invariants() -> None:
    index = HnswIndex.build(
        circle_points(),
        distance=Distance.COSINE,
        config=HnswConfig(m=6, ef_construct=32, ef_search=16, seed=11),
    )

    graph = index.export_graph()

    assert graph.entry_point is not None
    assert graph.max_level == max(graph.levels.values())
    for layer, adjacency in graph.layers.items():
        for point_id, neighbors in adjacency.items():
            assert len(neighbors) <= 6
            assert all(graph.levels[neighbor] >= layer for neighbor in neighbors)
            assert point_id not in neighbors

