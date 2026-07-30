from __future__ import annotations

from dataclasses import replace

from miniqdrant import CollectionConfig, Database, Distance, Point, SearchRequest
from miniqdrant.collection import _search
from miniqdrant.models import validate_point
from miniqdrant.segment import ImmutableSegment


def test_latest_version_wins_even_when_old_scores_higher(tmp_path) -> None:
    collection = Database.open(tmp_path).create_collection(
        "items",
        dimension=2,
        distance=Distance.DOT,
    )
    collection.upsert([Point(1, (10.0, 0.0), {"version": "old"})])
    collection.flush(indexed=True)
    collection.upsert([Point(1, (0.0, 1.0), {"version": "new"})])

    hits = collection.search(SearchRequest((1.0, 0.0), 10, exact=True)).hits

    assert len(hits) == 1
    assert hits[0].id == 1
    assert hits[0].score == 0.0
    assert hits[0].payload["version"] == "new"


def test_delete_overlay_hides_immutable_hnsw_hit(tmp_path) -> None:
    collection = Database.open(tmp_path).create_collection(
        "items",
        dimension=2,
        distance=Distance.DOT,
    )
    collection.upsert([Point(1, (1.0, 0.0), {})])
    collection.flush(indexed=True)

    collection.delete([1])

    assert collection.retrieve([1]) == ()
    assert collection.search(SearchRequest((1.0, 0.0), 10)).hits == ()


def test_cross_segment_topk_is_globally_ordered(tmp_path) -> None:
    collection = Database.open(tmp_path).create_collection(
        "items",
        dimension=2,
        distance=Distance.DOT,
    )
    collection.upsert([Point(1, (0.7, 0.0), {})])
    collection.flush()
    collection.upsert([Point(2, (0.9, 0.0), {})])
    collection.flush()
    collection.upsert([Point(3, (0.8, 0.0), {})])

    result = collection.search(SearchRequest((1.0, 0.0), 2, exact=True))

    assert [hit.id for hit in result.hits] == [2, 3]
    assert collection.count() == 3


def test_global_merge_deduplicates_same_version_point_copies() -> None:
    config = CollectionConfig(dimension=2, distance=Distance.DOT)
    point = replace(
        validate_point(Point(1, (1.0, 0.0), {}), config),
        version=1,
    )
    segment = ImmutableSegment.build(config, [point])

    result = _search(
        config,
        (segment, segment),
        {point.id: point},
        SearchRequest((1.0, 0.0), limit=10, exact=True),
    )

    assert [hit.id for hit in result.hits] == [1]


def test_many_stale_high_scores_cannot_hide_a_visible_lower_candidate(tmp_path) -> None:
    collection = Database.open(tmp_path).create_collection(
        "items",
        dimension=2,
        distance=Distance.DOT,
    )
    collection.upsert(
        [
            *(
                Point(point_id, (11.0 - point_id, 0.0), {})
                for point_id in range(1, 6)
            ),
            Point(99, (5.0, 0.0), {}),
        ]
    )
    collection.flush()
    collection.upsert(
        [
            Point(point_id, (point_id / 10.0, 0.0), {})
            for point_id in range(1, 6)
        ]
    )
    collection.flush()

    result = collection.search(SearchRequest((1.0, 0.0), limit=1, exact=True))

    assert [hit.id for hit in result.hits] == [99]
