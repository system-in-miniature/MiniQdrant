from __future__ import annotations

from collections.abc import Iterable, Mapping

from miniqdrant.config import CollectionConfig
from miniqdrant.filters.index import PayloadSchema
from miniqdrant.ids import PointId
from miniqdrant.models import StoredPoint
from miniqdrant.segment.codec import SegmentImage


def select_latest(records: Iterable[StoredPoint]) -> dict[PointId, StoredPoint]:
    latest: dict[PointId, StoredPoint] = {}
    for record in records:
        current = latest.get(record.id)
        if current is None or record.version > current.version:
            latest[record.id] = record
    return latest


def build_replacement(
    *,
    segment_id: str,
    config: CollectionConfig,
    records: Iterable[StoredPoint],
    payload_schemas: Mapping[str, PayloadSchema],
    drop_tombstones: bool,
) -> SegmentImage:
    latest = select_latest(records)
    return SegmentImage.build(
        segment_id=segment_id,
        config=config,
        records=(
            record
            for record in latest.values()
            if not drop_tombstones or not record.deleted
        ),
        payload_schemas=payload_schemas,
        indexed=True,
    )
