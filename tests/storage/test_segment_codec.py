from __future__ import annotations

import os

import pytest

from miniqdrant.config import CollectionConfig, Distance, HnswConfig
from miniqdrant.errors import CorruptionError
from miniqdrant.filters.index import PayloadSchema
from miniqdrant.models import Point
from miniqdrant.segment import MutableSegment
from miniqdrant.segment.codec import SegmentCodec, SegmentImage


def image() -> SegmentImage:
    config = CollectionConfig(
        dimension=2,
        distance=Distance.COSINE,
        hnsw=HnswConfig(m=4, ef_construct=16, ef_search=8, seed=9),
    )
    mutable = MutableSegment(config)
    mutable.create_payload_index("kind", PayloadSchema.KEYWORD)
    mutable.apply_upsert(Point(1, (1.0, 0.0), {"kind": "book"}), version=1)
    mutable.apply_upsert(Point(2, (0.0, 1.0), {"kind": "movie"}), version=2)
    mutable.apply_delete(3, version=3)
    return SegmentImage.build(
        segment_id="seg-test",
        config=config,
        records=mutable.iter_records(),
        payload_schemas=mutable.payload_indexes.schemas,
        indexed=True,
    )


def test_segment_round_trip_preserves_semantics(tmp_path) -> None:
    original = image()

    path = SegmentCodec.write_atomic(tmp_path / "segments", original)
    restored = SegmentCodec.read(path)

    assert restored.semantic_fingerprint() == original.semantic_fingerprint()
    assert restored.to_segment().search_exact((1.0, 0.0), limit=1)[0].point_id == 1
    assert {
        "meta.json",
        "points.bin",
        "payloads.bin",
        "versions.bin",
        "deleted.bin",
        "hnsw.bin",
        "payload-indexes.bin",
    } <= {item.name for item in path.iterdir()}


def test_segment_checksum_corruption_is_fatal(tmp_path) -> None:
    path = SegmentCodec.write_atomic(tmp_path / "segments", image())
    points = path / "points.bin"
    with points.open("r+b") as stream:
        stream.seek(-1, os.SEEK_END)
        value = stream.read(1)
        stream.seek(-1, os.SEEK_END)
        stream.write(bytes([value[0] ^ 0xFF]))

    with pytest.raises(CorruptionError, match="checksum"):
        SegmentCodec.read(path)


def test_existing_segment_is_never_overwritten(tmp_path) -> None:
    root = tmp_path / "segments"
    SegmentCodec.write_atomic(root, image())

    with pytest.raises(FileExistsError):
        SegmentCodec.write_atomic(root, image())

