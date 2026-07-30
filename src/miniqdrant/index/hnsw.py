"""Deterministic, inspectable HNSW construction and candidate search.

The implementation keeps the recognizable HNSW layer/entry-point algorithm,
but favors reproducibility over production recall and latency behavior.  In
particular, disconnected components are searched by non-standard restarts.
"""

from __future__ import annotations

import hashlib
import heapq
from collections.abc import Iterable, Set
from dataclasses import dataclass

from miniqdrant.config import Distance, HnswConfig
from miniqdrant.ids import PointId, point_id_bytes, point_id_sort_key
from miniqdrant.metrics import score
from miniqdrant.models import StoredPoint, Vector, normalize_cosine, validate_vector
from miniqdrant.segment.base import ScoredCandidate
from miniqdrant.topk import TopK


@dataclass(frozen=True, slots=True)
class HnswGraph:
    entry_point: PointId | None
    max_level: int
    levels: dict[PointId, int]
    layers: dict[int, dict[PointId, tuple[PointId, ...]]]


@dataclass(frozen=True, slots=True)
class HnswSearchResult:
    candidates: tuple[ScoredCandidate, ...]
    visited_count: int


class HnswIndex:
    def __init__(
        self,
        distance: Distance,
        config: HnswConfig,
        points: Iterable[StoredPoint],
    ) -> None:
        self._distance = distance
        self._config = config
        ordered = sorted(points, key=lambda point: point_id_sort_key(point.id))
        self._vectors = {point.id: point.vector for point in ordered}
        self._versions = {point.id: point.version for point in ordered}
        self._dimension = len(ordered[0].vector) if ordered else 0
        self._levels: dict[PointId, int] = {}
        self._layers: dict[int, dict[PointId, set[PointId]]] = {}
        self._deleted: set[PointId] = {
            point.id for point in ordered if point.deleted
        }
        self._entry_point: PointId | None = None
        self._max_level = -1
        # HNSW is a hierarchy of increasingly sparse proximity graphs.  Most
        # points live only at layer 0; the deterministic geometric-like level
        # assignment promotes a shrinking subset to act as long-range routes.
        for point in ordered:
            self._insert(point.id)

    @classmethod
    def build(
        cls,
        points: Iterable[StoredPoint],
        *,
        distance: Distance,
        config: HnswConfig,
    ) -> HnswIndex:
        return cls(distance, config, points)

    def mark_deleted(self, point_id: PointId) -> None:
        if point_id in self._vectors:
            self._deleted.add(point_id)

    def export_graph(self) -> HnswGraph:
        return HnswGraph(
            entry_point=self._entry_point,
            max_level=self._max_level,
            levels=dict(self._levels),
            layers={
                layer: {
                    point_id: tuple(sorted(neighbors, key=point_id_sort_key))
                    for point_id, neighbors in sorted(
                        adjacency.items(),
                        key=lambda item: point_id_sort_key(item[0]),
                    )
                }
                for layer, adjacency in sorted(self._layers.items())
            },
        )

    def search(
        self,
        query: Vector,
        *,
        limit: int,
        ef_search: int | None = None,
        allowed_ids: Set[PointId] | None = None,
    ) -> HnswSearchResult:
        if limit < 1:
            raise ValueError("search limit must be positive")
        if self._entry_point is None:
            return HnswSearchResult((), 0)
        normalized = validate_vector(query, self._dimension)
        if self._distance is Distance.COSINE:
            normalized = normalize_cosine(normalized)
        breadth = max(limit, ef_search or self._config.ef_search)
        entry = self._entry_point
        visited: set[PointId] = {entry}
        # Descend through sparse upper layers greedily.  The closest point found
        # at one layer becomes the entry point for the denser layer below.
        for layer in range(self._max_level, 0, -1):
            entry, layer_visited = self._greedy(normalized, entry, layer)
            visited.update(layer_visited)
        scores, layer_visited = self._search_layer(normalized, (entry,), breadth, 0)
        visited.update(layer_visited)
        # This restart loop is deliberately *not* standard HNSW.  It visits the
        # smallest-id unvisited component until `breadth` candidates exist,
        # making disconnected graphs easier to inspect and recall tests less
        # brittle.  When components are small (or ef is large), it can restart
        # repeatedly and turn an approximate graph search into a full scan.
        while len(scores) < breadth and len(visited) < len(self._vectors):
            next_entry = min(
                self._vectors.keys() - visited,
                key=point_id_sort_key,
            )
            additional_scores, additional_visited = self._search_layer(
                normalized,
                (next_entry,),
                breadth,
                0,
            )
            scores.update(additional_scores)
            visited.update(additional_visited)
        collector = TopK(limit)
        for point_id, point_score in scores.items():
            if point_id in self._deleted:
                continue
            if allowed_ids is not None and point_id not in allowed_ids:
                continue
            collector.offer(point_id, point_score)
        candidates = tuple(
            ScoredCandidate(item.point_id, item.score, self._versions[item.point_id])
            for item in collector.results()
        )
        return HnswSearchResult(candidates, len(visited))

    def _insert(self, point_id: PointId) -> None:
        level = _deterministic_level(point_id, self._config.seed)
        self._levels[point_id] = level
        for layer in range(level + 1):
            self._layers.setdefault(layer, {})[point_id] = set()
        if self._entry_point is None:
            self._entry_point = point_id
            self._max_level = level
            return

        entry = self._entry_point
        vector = self._vectors[point_id]
        # New points first use upper layers only for navigation; connections
        # are created once the descent reaches a layer occupied by the point.
        for layer in range(self._max_level, level, -1):
            entry, _ = self._greedy(vector, entry, layer)
        for layer in range(min(level, self._max_level), -1, -1):
            scores, _ = self._search_layer(
                vector,
                (entry,),
                self._config.ef_construct,
                layer,
            )
            neighbors = [
                candidate_id
                for candidate_id, _ in sorted(
                    scores.items(),
                    key=lambda item: (-item[1], point_id_sort_key(item[0])),
                )
                if candidate_id != point_id
            ][: self._config.m]
            for neighbor in neighbors:
                self._layers[layer][point_id].add(neighbor)
                self._layers[layer][neighbor].add(point_id)
                self._prune(neighbor, layer)
            self._prune(point_id, layer)
            if neighbors:
                entry = neighbors[0]
        if level > self._max_level:
            self._entry_point = point_id
            self._max_level = level

    def _greedy(
        self,
        query: Vector,
        entry: PointId,
        layer: int,
    ) -> tuple[PointId, set[PointId]]:
        current = entry
        current_score = score(self._distance, query, self._vectors[current])
        visited = {current}
        changed = True
        while changed:
            changed = False
            for neighbor in self._layers.get(layer, {}).get(current, ()):
                visited.add(neighbor)
                neighbor_score = score(self._distance, query, self._vectors[neighbor])
                if _better(neighbor, neighbor_score, current, current_score):
                    current = neighbor
                    current_score = neighbor_score
                    changed = True
        return current, visited

    def _search_layer(
        self,
        query: Vector,
        entries: Iterable[PointId],
        breadth: int,
        layer: int,
    ) -> tuple[dict[PointId, float], set[PointId]]:
        visited: set[PointId] = set()
        scores: dict[PointId, float] = {}
        frontier: list[tuple[float, tuple[int, int], PointId]] = []
        best: list[PointId] = []
        for entry in entries:
            if entry in visited:
                continue
            visited.add(entry)
            entry_score = score(self._distance, query, self._vectors[entry])
            scores[entry] = entry_score
            heapq.heappush(
                frontier,
                (-entry_score, point_id_sort_key(entry), entry),
            )
            best.append(entry)

        while frontier:
            negative_score, _, current = heapq.heappop(frontier)
            current_score = -negative_score
            best = _best_ids(best, scores, breadth)
            # `best` is the ef-sized convergence window.  Because the frontier
            # is ordered best-first, once its next candidate is worse than the
            # window's worst member, no queued expansion can improve the set.
            if len(best) >= breadth and current_score < scores[best[-1]]:
                break
            for neighbor in self._layers.get(layer, {}).get(current, ()):
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                neighbor_score = score(self._distance, query, self._vectors[neighbor])
                scores[neighbor] = neighbor_score
                best = _best_ids([*best, neighbor], scores, breadth)
                if neighbor in best:
                    heapq.heappush(
                        frontier,
                        (-neighbor_score, point_id_sort_key(neighbor), neighbor),
                    )
        return {point_id: scores[point_id] for point_id in best}, visited

    def _prune(self, point_id: PointId, layer: int) -> None:
        neighbors = self._layers[layer][point_id]
        if len(neighbors) <= self._config.m:
            return
        # Keep the m closest neighbors (with stable ID tie-breaking) and remove
        # reverse edges too.  Production HNSW commonly uses a diversity-aware
        # heuristic; this nearest-only rule is smaller and deterministic but
        # can create less navigable clusters and disconnected components.
        retained = set(
            sorted(
                neighbors,
                key=lambda neighbor: (
                    -score(
                        self._distance,
                        self._vectors[point_id],
                        self._vectors[neighbor],
                    ),
                    point_id_sort_key(neighbor),
                ),
            )[: self._config.m]
        )
        removed = neighbors.difference(retained)
        self._layers[layer][point_id] = retained
        for neighbor in removed:
            self._layers[layer][neighbor].discard(point_id)


def _deterministic_level(point_id: PointId, seed: int, maximum: int = 16) -> int:
    digest = hashlib.blake2b(
        seed.to_bytes(8, "big", signed=True) + point_id_bytes(point_id),
        digest_size=8,
    ).digest()
    bits = int.from_bytes(digest, "big")
    level = 0
    while level < maximum and bits & 1:
        level += 1
        bits >>= 1
    return level


def _best_ids(
    point_ids: Iterable[PointId],
    scores: dict[PointId, float],
    breadth: int,
) -> list[PointId]:
    return sorted(
        set(point_ids),
        key=lambda point_id: (-scores[point_id], point_id_sort_key(point_id)),
    )[:breadth]


def _better(
    left_id: PointId,
    left_score: float,
    right_id: PointId,
    right_score: float,
) -> bool:
    if left_score != right_score:
        return left_score > right_score
    return point_id_sort_key(left_id) < point_id_sort_key(right_id)
