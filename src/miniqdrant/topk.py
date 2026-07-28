from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import Self

from miniqdrant.ids import PointId, point_id_sort_key


@dataclass(frozen=True, slots=True)
class Candidate:
    point_id: PointId
    score: float


@dataclass(frozen=True, slots=True)
class _WorstFirst:
    candidate: Candidate

    def __lt__(self, other: Self) -> bool:
        left = self.candidate
        right = other.candidate
        if left.score != right.score:
            return left.score < right.score
        return point_id_sort_key(left.point_id) > point_id_sort_key(right.point_id)


class TopK:
    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise ValueError("TopK capacity must be positive")
        self._capacity = capacity
        self._heap: list[_WorstFirst] = []

    def __len__(self) -> int:
        return len(self._heap)

    def offer(self, point_id: PointId, score: float) -> None:
        if not math.isfinite(score):
            raise ValueError("candidate score must be finite")
        entry = _WorstFirst(Candidate(point_id, score))
        if len(self._heap) < self._capacity:
            heapq.heappush(self._heap, entry)
            return
        if _is_better(entry.candidate, self._heap[0].candidate):
            heapq.heapreplace(self._heap, entry)

    def results(self) -> tuple[Candidate, ...]:
        return tuple(
            sorted(
                (entry.candidate for entry in self._heap),
                key=lambda item: (-item.score, point_id_sort_key(item.point_id)),
            )
        )


def _is_better(left: Candidate, right: Candidate) -> bool:
    if left.score != right.score:
        return left.score > right.score
    return point_id_sort_key(left.point_id) < point_id_sort_key(right.point_id)

