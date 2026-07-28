from __future__ import annotations

from collections.abc import Iterable

from miniqdrant.config import Distance
from miniqdrant.filters import Filter, matches_filter
from miniqdrant.metrics import score
from miniqdrant.models import StoredPoint, Vector
from miniqdrant.segment.base import ScoredCandidate, SegmentSearchResult
from miniqdrant.topk import TopK


class PlainVectorIndex:
    def __init__(self, distance: Distance, points: Iterable[StoredPoint]) -> None:
        self._distance = distance
        self._points = tuple(points)
        self._versions = {point.id: point.version for point in self._points}

    def search(
        self,
        query: Vector,
        limit: int,
        filter_: Filter | None = None,
    ) -> tuple[ScoredCandidate, ...]:
        return self.search_with_stats(query, limit, filter_).candidates

    def search_with_stats(
        self,
        query: Vector,
        limit: int,
        filter_: Filter | None = None,
    ) -> SegmentSearchResult:
        collector = TopK(limit)
        visited = 0
        for point in self._points:
            if point.deleted:
                continue
            visited += 1
            if not matches_filter(point.id, point.payload, filter_):
                continue
            collector.offer(point.id, score(self._distance, query, point.vector))
        candidates = tuple(
            ScoredCandidate(item.point_id, item.score, self._versions[item.point_id])
            for item in collector.results()
        )
        return SegmentSearchResult(candidates, visited, "exact_full_scan")

