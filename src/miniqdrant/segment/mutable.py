from __future__ import annotations

from dataclasses import replace

from miniqdrant.config import CollectionConfig, Distance
from miniqdrant.filters.index import PayloadIndexSet, PayloadSchema
from miniqdrant.ids import PointId, canonicalize_point_id
from miniqdrant.index.plain import PlainVectorIndex
from miniqdrant.json_values import freeze_json_object
from miniqdrant.models import Point, StoredPoint, normalize_cosine, validate_point, validate_vector
from miniqdrant.segment.base import SegmentSearchRequest, SegmentSearchResult


class MutableSegment:
    def __init__(self, config: CollectionConfig) -> None:
        self._config = config
        self._records: dict[PointId, StoredPoint] = {}
        self._payload_indexes = PayloadIndexSet()

    @property
    def payload_indexes(self) -> PayloadIndexSet:
        return self._payload_indexes

    @property
    def live_count(self) -> int:
        return sum(not record.deleted for record in self._records.values())

    @property
    def total_count(self) -> int:
        return len(self._records)

    def version_of(self, point_id: object) -> int | None:
        record = self._records.get(canonicalize_point_id(point_id))
        return None if record is None else record.version

    def get(self, point_id: object) -> StoredPoint | None:
        record = self._records.get(canonicalize_point_id(point_id))
        if record is None or record.deleted:
            return None
        return record

    def iter_live(self) -> tuple[StoredPoint, ...]:
        return tuple(record for record in self._records.values() if not record.deleted)

    def iter_records(self) -> tuple[StoredPoint, ...]:
        return tuple(self._records.values())

    def create_payload_index(self, path: str, schema: PayloadSchema) -> None:
        self._payload_indexes.create(path, schema, self.iter_live())

    def apply_upsert(self, point: Point, version: int) -> bool:
        if version < 1:
            raise ValueError("point version must be positive")
        validated = validate_point(point, self._config)
        current = self._records.get(validated.id)
        if current is not None and current.version >= version:
            return False
        stored = replace(validated, version=version)
        self._records[validated.id] = stored
        self._payload_indexes.upsert(stored)
        return True

    def apply_delete(self, point_id: object, version: int) -> bool:
        if version < 1:
            raise ValueError("point version must be positive")
        canonical = canonicalize_point_id(point_id)
        current = self._records.get(canonical)
        if current is not None and current.version >= version:
            return False
        self._records[canonical] = StoredPoint(
            id=canonical,
            vector=(),
            payload=freeze_json_object({}),
            version=version,
            deleted=True,
        )
        self._payload_indexes.delete(canonical)
        return True

    def search(self, request: SegmentSearchRequest) -> SegmentSearchResult:
        query = validate_vector(request.vector, self._config.dimension)
        if self._config.distance is Distance.COSINE:
            query = normalize_cosine(query)
        candidate_set = self._payload_indexes.candidates(request.filter)
        points = tuple(
            point for point in self.iter_live() if point.id in candidate_set.ids
        )
        index = PlainVectorIndex(self._config.distance, points)
        return index.search_with_stats(query, request.limit, candidate_set.residual)
