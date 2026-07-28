from __future__ import annotations

import math
from collections.abc import Iterable
from pathlib import Path
from threading import RLock

from miniqdrant.config import CollectionConfig
from miniqdrant.errors import InvalidFilterError
from miniqdrant.filters import Filter
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
from miniqdrant.segment import MutableSegment, SegmentSearchRequest


class Collection(Lifecycle):
    def __init__(self, name: str, path: Path, config: CollectionConfig) -> None:
        super().__init__()
        self._name = name
        self._path = path
        self._config = config
        self._update_lock = RLock()
        self._mutable = MutableSegment(config)
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
            return self._mutable.live_count

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

    def retrieve(self, point_ids: Iterable[object]) -> tuple[StoredPoint, ...]:
        self._ensure_open()
        identifiers = tuple(canonicalize_point_id(item) for item in point_ids)
        with self._update_lock:
            return tuple(
                point
                for point_id in identifiers
                if (point := self._mutable.get(point_id)) is not None
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
            segment_result = self._mutable.search(
                SegmentSearchRequest(
                    vector=tuple(request.vector),
                    limit=request.limit,
                    filter=request.filter,
                    exact=request.exact,
                    ef_search=request.ef_search,
                )
            )
            hits = tuple(
                hit
                for candidate in segment_result.candidates
                if (
                    request.score_threshold is None
                    or candidate.score >= request.score_threshold
                )
                if (
                    hit := self._project_hit(
                        candidate.point_id,
                        candidate.score,
                        request,
                    )
                )
                is not None
            )
            return SearchResult(hits, plan=segment_result.strategy)

    def close(self) -> None:
        self._mark_closed()

    def _next_version(self) -> int:
        self._version += 1
        return self._version

    def _project_hit(
        self,
        point_id: PointId,
        score: float,
        request: SearchRequest,
    ) -> SearchHit | None:
        point = self._mutable.get(point_id)
        if point is None:
            return None
        return SearchHit(
            id=point.id,
            score=score,
            payload=point.payload if request.with_payload else None,
            vector=point.vector if request.with_vector else None,
        )

