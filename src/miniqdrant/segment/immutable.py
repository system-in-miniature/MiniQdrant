from __future__ import annotations

from collections.abc import Iterable, Mapping

from miniqdrant.config import CollectionConfig, Distance
from miniqdrant.filters import matches_filter
from miniqdrant.filters.index import PayloadIndexSet, PayloadSchema
from miniqdrant.ids import PointId
from miniqdrant.index.hnsw import HnswIndex
from miniqdrant.index.plain import PlainVectorIndex
from miniqdrant.index.quantization import ScalarQuantizedIndex
from miniqdrant.models import StoredPoint, normalize_cosine, validate_vector
from miniqdrant.query.executor import execute_quantized_rescore
from miniqdrant.query.planner import QueryPlanner, SegmentFacts, Strategy
from miniqdrant.segment.base import (
    ScoredCandidate,
    SegmentSearchRequest,
    SegmentSearchResult,
)


class ImmutableSegment:
    def __init__(
        self,
        config: CollectionConfig,
        records: Iterable[StoredPoint],
        *,
        payload_schemas: Mapping[str, PayloadSchema] | None = None,
        indexed: bool = False,
    ) -> None:
        self._config = config
        self._records = _highest_versions(records)
        self._payload_indexes = PayloadIndexSet(
            point.id for point in self._records.values() if not point.deleted
        )
        for path, schema in (payload_schemas or {}).items():
            self._payload_indexes.create(path, schema, self.iter_live())
        self._hnsw = (
            HnswIndex.build(
                self.iter_live(),
                distance=config.distance,
                config=config.hnsw,
            )
            if indexed and self.live_count
            else None
        )
        self._quantized = (
            ScalarQuantizedIndex(config.distance, self.iter_live())
            if indexed and config.quantization is not None and self.live_count
            else None
        )

    @classmethod
    def build(
        cls,
        config: CollectionConfig,
        records: Iterable[StoredPoint],
        *,
        payload_schemas: Mapping[str, PayloadSchema] | None = None,
        indexed: bool = False,
    ) -> ImmutableSegment:
        return cls(
            config,
            records,
            payload_schemas=payload_schemas,
            indexed=indexed,
        )

    @property
    def live_count(self) -> int:
        return sum(not point.deleted for point in self._records.values())

    @property
    def total_count(self) -> int:
        return len(self._records)

    @property
    def deleted_count(self) -> int:
        return self.total_count - self.live_count

    @property
    def indexed(self) -> bool:
        return self._hnsw is not None

    @property
    def payload_schemas(self) -> dict[str, PayloadSchema]:
        return self._payload_indexes.schemas

    def get_record(self, point_id: PointId) -> StoredPoint | None:
        return self._records.get(point_id)

    def get(self, point_id: PointId) -> StoredPoint | None:
        record = self._records.get(point_id)
        if record is None or record.deleted:
            return None
        return record

    def iter_records(self) -> tuple[StoredPoint, ...]:
        return tuple(self._records.values())

    def iter_live(self) -> tuple[StoredPoint, ...]:
        return tuple(point for point in self._records.values() if not point.deleted)

    def create_payload_index(self, path: str, schema: PayloadSchema) -> None:
        self._payload_indexes.create(path, schema, self.iter_live())

    def search_exact(
        self,
        query: tuple[float, ...],
        *,
        limit: int,
    ) -> tuple[ScoredCandidate, ...]:
        return self.search(
            SegmentSearchRequest(query, limit, exact=True)
        ).candidates

    def search(self, request: SegmentSearchRequest) -> SegmentSearchResult:
        query = validate_vector(request.vector, self._config.dimension)
        if self._config.distance is Distance.COSINE:
            query = normalize_cosine(query)
        candidates = self._payload_indexes.candidates(request.filter)
        planner = QueryPlanner(
            plain_threshold=self._config.optimizer.indexing_threshold_points,
            filter_scan_threshold=self._config.optimizer.indexing_threshold_points,
        )
        plan = planner.choose(
            SegmentFacts(
                total_points=self.live_count,
                filtered=candidates.estimate if request.filter is not None else None,
                has_hnsw=self._hnsw is not None,
                has_quantization=self._quantized is not None,
                exact_requested=request.exact,
            )
        )
        if plan.strategy in (Strategy.EXACT_FULL_SCAN, Strategy.FILTER_THEN_EXACT):
            points = (
                point for point in self.iter_live() if point.id in candidates.ids
            )
            result = PlainVectorIndex(self._config.distance, points).search_with_stats(
                query,
                request.limit,
                candidates.residual,
            )
            return SegmentSearchResult(
                result.candidates,
                result.visited_count,
                plan.strategy.value,
            )

        if plan.strategy is Strategy.QUANTIZED_HNSW_RESCORE:
            assert self._quantized is not None
            assert self._config.quantization is not None
            result, visited = execute_quantized_rescore(
                self._quantized,
                query,
                candidates,
                limit=request.limit,
                oversampling=self._config.quantization.oversampling,
            )
            return SegmentSearchResult(result, visited, plan.strategy.value)

        assert self._hnsw is not None
        local_limit = min(
            self.live_count,
            max(request.limit, request.limit * 4 if request.filter is not None else 0),
        )
        graph_result = self._hnsw.search(
            query,
            limit=local_limit,
            ef_search=request.ef_search,
            allowed_ids=candidates.ids if request.filter is not None else None,
        )
        filtered = tuple(
            candidate
            for candidate in graph_result.candidates
            if (
                point := self.get(candidate.point_id)
            ) is not None
            and matches_filter(point.id, point.payload, candidates.residual)
        )[: request.limit]
        return SegmentSearchResult(
            filtered,
            graph_result.visited_count,
            plan.strategy.value,
        )


def _highest_versions(records: Iterable[StoredPoint]) -> dict[PointId, StoredPoint]:
    highest: dict[PointId, StoredPoint] = {}
    for record in records:
        current = highest.get(record.id)
        if current is None or record.version > current.version:
            highest[record.id] = record
    return highest
