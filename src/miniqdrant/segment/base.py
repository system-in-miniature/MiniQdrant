from __future__ import annotations

from dataclasses import dataclass

from miniqdrant.filters import Filter
from miniqdrant.ids import PointId
from miniqdrant.models import Vector


@dataclass(frozen=True, slots=True)
class SegmentSearchRequest:
    vector: Vector
    limit: int
    filter: Filter | None = None
    exact: bool = False
    ef_search: int | None = None

    def __post_init__(self) -> None:
        if self.limit < 1:
            raise ValueError("search limit must be positive")
        if self.ef_search is not None and self.ef_search < 1:
            raise ValueError("ef_search must be positive")


@dataclass(frozen=True, slots=True)
class ScoredCandidate:
    point_id: PointId
    score: float
    version: int


@dataclass(frozen=True, slots=True)
class SegmentSearchResult:
    candidates: tuple[ScoredCandidate, ...]
    visited_count: int
    strategy: str

