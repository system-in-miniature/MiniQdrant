from __future__ import annotations

from miniqdrant.config import CollectionConfig, Distance, HnswConfig, OptimizerConfig
from miniqdrant.filters import Filter, Match
from miniqdrant.filters.index import PayloadSchema
from miniqdrant.models import Point
from miniqdrant.segment import ImmutableSegment, MutableSegment, SegmentSearchRequest


def indexed_segment() -> ImmutableSegment:
    config = CollectionConfig(
        dimension=2,
        distance=Distance.DOT,
        hnsw=HnswConfig(m=4, ef_construct=16, ef_search=8, seed=4),
        optimizer=OptimizerConfig(
            flush_threshold_points=10,
            indexing_threshold_points=1,
            target_segment_count=2,
        ),
    )
    mutable = MutableSegment(config)
    mutable.create_payload_index("kind", PayloadSchema.KEYWORD)
    for point_id in range(1, 21):
        mutable.apply_upsert(
            Point(
                point_id,
                (float(point_id), 1.0),
                {"kind": "book" if point_id % 2 else "movie"},
            ),
            version=point_id,
        )
    return ImmutableSegment.build(
        config,
        mutable.iter_records(),
        payload_schemas=mutable.payload_indexes.schemas,
        indexed=True,
    )


def test_large_indexed_segment_uses_hnsw() -> None:
    segment = indexed_segment()

    result = segment.search(
        SegmentSearchRequest(vector=(1.0, 0.0), limit=3, exact=False)
    )

    assert result.strategy == "hnsw"
    assert [item.point_id for item in result.candidates] == [20, 19, 18]


def test_filtered_hnsw_never_returns_residual_mismatch() -> None:
    segment = indexed_segment()

    result = segment.search(
        SegmentSearchRequest(
            vector=(1.0, 0.0),
            limit=5,
            filter=Filter(must=(Match("kind", "book"),)),
            exact=False,
        )
    )

    assert result.strategy == "filtered_hnsw"
    assert all(segment.get(item.point_id).payload["kind"] == "book" for item in result.candidates)


def test_exact_request_bypasses_hnsw() -> None:
    result = indexed_segment().search(
        SegmentSearchRequest(vector=(1.0, 0.0), limit=3, exact=True)
    )

    assert result.strategy == "exact_full_scan"

