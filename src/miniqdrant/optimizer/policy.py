from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from miniqdrant.config import OptimizerConfig


class OptimizationKind(StrEnum):
    VACUUM = "vacuum"
    MERGE = "merge"
    INDEX = "index"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class SegmentCandidate:
    segment_id: str
    live_points: int
    deleted_points: int
    indexed: bool

    @property
    def total_points(self) -> int:
        return self.live_points + self.deleted_points

    @property
    def deleted_ratio(self) -> float:
        if self.total_points == 0:
            return 0.0
        return self.deleted_points / self.total_points


@dataclass(frozen=True, slots=True)
class OptimizationPlan:
    kind: OptimizationKind
    segment_ids: tuple[str, ...]


def choose_optimization(
    candidates: tuple[SegmentCandidate, ...],
    config: OptimizerConfig,
) -> OptimizationPlan:
    stale = tuple(
        candidate
        for candidate in candidates
        if candidate.deleted_ratio >= config.deleted_ratio_threshold
    )
    if stale:
        selected = min(stale, key=lambda item: (-item.deleted_ratio, item.segment_id))
        return OptimizationPlan(OptimizationKind.VACUUM, (selected.segment_id,))

    if len(candidates) > config.target_segment_count:
        smallest = sorted(
            candidates,
            key=lambda item: (item.total_points, item.segment_id),
        )[:2]
        return OptimizationPlan(
            OptimizationKind.MERGE,
            tuple(candidate.segment_id for candidate in smallest),
        )

    plain = tuple(
        candidate
        for candidate in candidates
        if not candidate.indexed
        and candidate.live_points >= config.indexing_threshold_points
    )
    if plain:
        selected = min(plain, key=lambda item: (-item.live_points, item.segment_id))
        return OptimizationPlan(OptimizationKind.INDEX, (selected.segment_id,))

    return OptimizationPlan(OptimizationKind.NONE, ())
