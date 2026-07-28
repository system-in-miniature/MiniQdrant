from __future__ import annotations

import math
from collections.abc import Iterable
from pathlib import Path
from threading import RLock

from miniqdrant.config import CollectionConfig
from miniqdrant.errors import InvalidFilterError
from miniqdrant.filters import Filter
from miniqdrant.filters.index import PayloadSchema
from miniqdrant.ids import PointId, canonicalize_point_id
from miniqdrant.lifecycle import Lifecycle
from miniqdrant.models import (
    Point,
    SearchHit,
    SearchRequest,
    SearchResult,
    StoredPoint,
    validate_point,
)
from miniqdrant.segment import ImmutableSegment, MutableSegment, SegmentSearchRequest
from miniqdrant.topk import TopK


class Collection(Lifecycle):
    def __init__(self, name: str, path: Path, config: CollectionConfig) -> None:
        super().__init__()
        self._name = name
        self._path = path
        self._config = config
        self._update_lock = RLock()
        self._mutable = MutableSegment(config)
        self._segments: list[ImmutableSegment] = []
        self._version = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def path(self) -> Path:
        return self._path

    @property
    def config(self) -> CollectionConfig:
        return self._config

    def count(self) -> int:
        self._ensure_open()
        with self._update_lock:
            return sum(not point.deleted for point in self._latest_records().values())

    def upsert(self, points: Iterable[Point]) -> int:
        self._ensure_open()
        batch = tuple(points)
        if not batch:
            raise ValueError("upsert batch must not be empty")
        for point in batch:
            validate_point(point, self._config)
        with self._update_lock:
            version = self._next_version()
            for point in batch:
                self._mutable.apply_upsert(point, version)
            return version

    def delete(self, point_ids: Iterable[object]) -> int:
        self._ensure_open()
        identifiers = tuple(canonicalize_point_id(item) for item in point_ids)
        if not identifiers:
            raise ValueError("delete batch must not be empty")
        with self._update_lock:
            version = self._next_version()
            for point_id in identifiers:
                self._mutable.apply_delete(point_id, version)
            return version

    def create_payload_index(self, path: str, schema: PayloadSchema | str) -> None:
        self._ensure_open()
        with self._update_lock:
            normalized = PayloadSchema(schema)
            self._mutable.create_payload_index(path, normalized)
            for segment in self._segments:
                segment.create_payload_index(path, normalized)

    def flush(self, *, indexed: bool = False) -> None:
        self._ensure_open()
        with self._update_lock:
            if self._mutable.total_count == 0:
                return
            schemas = self._mutable.payload_indexes.schemas
            segment = ImmutableSegment.build(
                self._config,
                self._mutable.iter_records(),
                payload_schemas=schemas,
                indexed=indexed,
            )
            self._segments.append(segment)
            self._mutable = MutableSegment(self._config)
            for path, schema in schemas.items():
                self._mutable.create_payload_index(path, schema)

    def retrieve(self, point_ids: Iterable[object]) -> tuple[StoredPoint, ...]:
        self._ensure_open()
        identifiers = tuple(canonicalize_point_id(item) for item in point_ids)
        with self._update_lock:
            latest = self._latest_records()
            return tuple(
                point
                for point_id in identifiers
                if (point := latest.get(point_id)) is not None and not point.deleted
            )

    def search(self, request: SearchRequest) -> SearchResult:
        self._ensure_open()
        if request.limit < 1:
            raise ValueError("search limit must be positive")
        if request.filter is not None and not isinstance(request.filter, Filter):
            raise InvalidFilterError("search filter must be a Filter")
        if request.score_threshold is not None and not math.isfinite(request.score_threshold):
            raise ValueError("score threshold must be finite")
        with self._update_lock:
            latest = self._latest_records()
            search_segments = [*self._segments, self._mutable]
            local_limit = request.limit + max(0, len(search_segments) - 1)
            segment_results = tuple(
                segment.search(
                    SegmentSearchRequest(
                        vector=tuple(request.vector),
                        limit=local_limit,
                        filter=request.filter,
                        exact=request.exact,
                        ef_search=request.ef_search,
                    )
                )
                for segment in search_segments
            )
            collector = TopK(request.limit)
            for result in segment_results:
                for candidate in result.candidates:
                    visible = latest.get(candidate.point_id)
                    if (
                        visible is None
                        or visible.deleted
                        or visible.version != candidate.version
                    ):
                        continue
                    if (
                        request.score_threshold is not None
                        and candidate.score < request.score_threshold
                    ):
                        continue
                    collector.offer(candidate.point_id, candidate.score)
            hits = tuple(
                self._project_hit(latest[item.point_id], item.score, request)
                for item in collector.results()
            )
            return SearchResult(
                hits,
                plan=tuple(result.strategy for result in segment_results),
            )

    def close(self) -> None:
        self._mark_closed()

    def _next_version(self) -> int:
        self._version += 1
        return self._version

    def _latest_records(self) -> dict[PointId, StoredPoint]:
        latest: dict[PointId, StoredPoint] = {}
        for segment in self._segments:
            for record in segment.iter_records():
                current = latest.get(record.id)
                if current is None or record.version > current.version:
                    latest[record.id] = record
        for record in self._mutable.iter_records():
            current = latest.get(record.id)
            if current is None or record.version > current.version:
                latest[record.id] = record
        return latest

    @staticmethod
    def _project_hit(
        point: StoredPoint,
        score: float,
        request: SearchRequest,
    ) -> SearchHit:
        return SearchHit(
            id=point.id,
            score=score,
            payload=point.payload if request.with_payload else None,
            vector=point.vector if request.with_vector else None,
        )
