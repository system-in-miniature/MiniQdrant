from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from miniqdrant.filters.cardinality import CardinalityEstimate


class Strategy(StrEnum):
    EXACT_FULL_SCAN = "exact_full_scan"
    FILTER_THEN_EXACT = "filter_then_exact"
    HNSW = "hnsw"
    FILTERED_HNSW = "filtered_hnsw"
    QUANTIZED_HNSW_RESCORE = "quantized_hnsw_rescore"


@dataclass(frozen=True, slots=True)
class SegmentFacts:
    total_points: int
    filtered: CardinalityEstimate | None = None
    has_hnsw: bool = True
    has_quantization: bool = False
    exact_requested: bool = False


@dataclass(frozen=True, slots=True)
class SearchPlan:
    strategy: Strategy
    reason: str
    total_points: int
    filtered: CardinalityEstimate | None


class QueryPlanner:
    def __init__(self, plain_threshold: int, filter_scan_threshold: int) -> None:
        if plain_threshold < 0 or filter_scan_threshold < 0:
            raise ValueError("planner thresholds must be non-negative")
        self._plain_threshold = plain_threshold
        self._filter_scan_threshold = filter_scan_threshold

    def choose(self, facts: SegmentFacts) -> SearchPlan:
        if facts.exact_requested:
            return self._plan(Strategy.EXACT_FULL_SCAN, "exact search requested", facts)
        if facts.total_points <= self._plain_threshold or not facts.has_hnsw:
            return self._plan(
                Strategy.EXACT_FULL_SCAN,
                "segment below plain-scan threshold",
                facts,
            )
        if (
            facts.filtered is not None
            and facts.filtered.maximum <= self._filter_scan_threshold
        ):
            return self._plan(
                Strategy.FILTER_THEN_EXACT,
                "indexed filter candidates below exact threshold",
                facts,
            )
        if facts.has_quantization:
            return self._plan(
                Strategy.QUANTIZED_HNSW_RESCORE,
                "quantized index available for approximate search",
                facts,
            )
        if facts.filtered is not None:
            return self._plan(
                Strategy.FILTERED_HNSW,
                "filtered population remains above exact threshold",
                facts,
            )
        return self._plan(Strategy.HNSW, "large unfiltered segment", facts)

    @staticmethod
    def _plan(strategy: Strategy, reason: str, facts: SegmentFacts) -> SearchPlan:
        return SearchPlan(strategy, reason, facts.total_points, facts.filtered)

