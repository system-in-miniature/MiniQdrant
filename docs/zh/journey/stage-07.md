# Stage 07 · 确定性 HNSW 搜索

### 目标

实现确定性 HNSW 搜索，并能从可执行反例、运行时状态与关键语句解释其边界。

??? note "交付文件"
    - `src/miniqdrant/index/__init__.py`
    - `src/miniqdrant/index/hnsw.py`
    - `tests/index/test_hnsw_graph.py`
    - `tests/index/test_hnsw_recall.py`
    - `tests/index/test_hnsw_search.py`

### 当前遇到的问题

近似最近邻检索需要显式 Graph Layer、Neighbor Bound、Entry Point、Traversal Budget 与 Tie Rule。

### 测试契约

#### 先看会坏在哪里

聚焦测试让确定性 HNSW 搜索经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

??? note "文件差异：tests/index/test_hnsw_graph.py"
    ```diff
    diff --git a/tests/index/test_hnsw_graph.py b/tests/index/test_hnsw_graph.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..1cf78f178d40980605108e540e354153b60aa7e1
    --- /dev/null
    +++ b/tests/index/test_hnsw_graph.py
    @@ -0,0 +1,54 @@
    +from __future__ import annotations
    +
    +import math
    +
    +from miniqdrant.config import CollectionConfig, Distance, HnswConfig
    +from miniqdrant.index.hnsw import HnswIndex
    +from miniqdrant.models import Point, validate_point
    +
    +
    +def circle_points(count: int = 40):
    +    config = CollectionConfig(dimension=2, distance=Distance.COSINE)
    +    return tuple(
    +        validate_point(
    +            Point(
    +                index,
    +                (
    +                    math.cos(2 * math.pi * index / count),
    +                    math.sin(2 * math.pi * index / count),
    +                ),
    +                {},
    +            ),
    +            config,
    +        )
    +        for index in range(count)
    +    )
    +
    +
    +def test_same_seed_builds_same_graph() -> None:
    +    points = circle_points()
    +    config = HnswConfig(m=6, ef_construct=32, ef_search=16, seed=7)
    +
    +    first = HnswIndex.build(points, distance=Distance.COSINE, config=config)
    +    second = HnswIndex.build(reversed(points), distance=Distance.COSINE, config=config)
    +
    +    assert first.export_graph() == second.export_graph()
    +
    +
    +def test_graph_respects_level_and_degree_invariants() -> None:
    +    index = HnswIndex.build(
    +        circle_points(),
    +        distance=Distance.COSINE,
    +        config=HnswConfig(m=6, ef_construct=32, ef_search=16, seed=11),
    +    )
    +
    +    graph = index.export_graph()
    +
    +    assert graph.entry_point is not None
    +    assert graph.max_level == max(graph.levels.values())
    +    for layer, adjacency in graph.layers.items():
    +        for point_id, neighbors in adjacency.items():
    +            assert len(neighbors) <= 6
    +            assert all(graph.levels[neighbor] >= layer for neighbor in neighbors)
    +            assert point_id not in neighbors
    +
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让确定性 HNSW 搜索经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert first.export_graph() == second.export_graph()
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/index/test_hnsw_recall.py"
    ```diff
    diff --git a/tests/index/test_hnsw_recall.py b/tests/index/test_hnsw_recall.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..658111bc6bf8af5512ec60ce06079cc6fe22b847
    --- /dev/null
    +++ b/tests/index/test_hnsw_recall.py
    @@ -0,0 +1,45 @@
    +from __future__ import annotations
    +
    +import random
    +
    +from miniqdrant.config import CollectionConfig, Distance, HnswConfig
    +from miniqdrant.index.hnsw import HnswIndex
    +from miniqdrant.index.plain import PlainVectorIndex
    +from miniqdrant.models import Point, normalize_cosine, validate_point
    +
    +
    +def test_hnsw_recall_reaches_required_floor() -> None:
    +    randomizer = random.Random(17)
    +    config = CollectionConfig(dimension=8, distance=Distance.COSINE)
    +    points = tuple(
    +        validate_point(
    +            Point(
    +                point_id,
    +                tuple(randomizer.uniform(-1.0, 1.0) for _ in range(config.dimension)),
    +                {},
    +            ),
    +            config,
    +        )
    +        for point_id in range(200)
    +    )
    +    exact = PlainVectorIndex(config.distance, points)
    +    approximate = HnswIndex.build(
    +        points,
    +        distance=config.distance,
    +        config=HnswConfig(m=12, ef_construct=64, ef_search=64, seed=19),
    +    )
    +    recalls = []
    +
    +    for _ in range(20):
    +        query = normalize_cosine(
    +            tuple(randomizer.uniform(-1.0, 1.0) for _ in range(config.dimension))
    +        )
    +        expected = {item.point_id for item in exact.search(query, limit=10)}
    +        actual = {
    +            item.point_id
    +            for item in approximate.search(query, limit=10, ef_search=64).candidates
    +        }
    +        recalls.append(len(actual.intersection(expected)) / len(expected))
    +
    +    assert sum(recalls) / len(recalls) >= 0.90
    +
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让确定性 HNSW 搜索经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert first.export_graph() == second.export_graph()
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/index/test_hnsw_search.py"
    ```diff
    diff --git a/tests/index/test_hnsw_search.py b/tests/index/test_hnsw_search.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..52bd8e2d50b9753c1229256a67fb076e07753e83
    --- /dev/null
    +++ b/tests/index/test_hnsw_search.py
    @@ -0,0 +1,46 @@
    +from __future__ import annotations
    +
    +from miniqdrant.config import CollectionConfig, Distance, HnswConfig
    +from miniqdrant.index.hnsw import HnswIndex
    +from miniqdrant.models import Point, validate_point
    +
    +
    +def build_index() -> HnswIndex:
    +    config = CollectionConfig(dimension=2, distance=Distance.DOT)
    +    points = tuple(
    +        validate_point(Point(index, (float(index), 1.0), {}), config)
    +        for index in range(1, 21)
    +    )
    +    return HnswIndex.build(
    +        points,
    +        distance=Distance.DOT,
    +        config=HnswConfig(m=6, ef_construct=24, ef_search=12, seed=3),
    +    )
    +
    +
    +def test_hnsw_returns_best_candidates_in_score_order() -> None:
    +    result = build_index().search((1.0, 0.0), limit=3, ef_search=16)
    +
    +    assert [candidate.point_id for candidate in result.candidates] == [20, 19, 18]
    +    assert result.visited_count >= 3
    +
    +
    +def test_hnsw_never_returns_deleted_or_disallowed_point() -> None:
    +    index = build_index()
    +    index.mark_deleted(20)
    +
    +    result = index.search(
    +        (1.0, 0.0),
    +        limit=10,
    +        ef_search=16,
    +        allowed_ids={18, 20},
    +    )
    +
    +    assert [candidate.point_id for candidate in result.candidates] == [18]
    +
    +
    +def test_ef_search_is_raised_to_limit() -> None:
    +    result = build_index().search((1.0, 0.0), limit=8, ef_search=2)
    +
    +    assert len(result.candidates) == 8
    +
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让确定性 HNSW 搜索经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert first.export_graph() == second.export_graph()
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是确定性 HNSW 搜索。近似最近邻检索需要显式 Graph Layer、Neighbor Bound、Entry Point、Traversal Budget 与 Tie Rule。

### 为什么需要这个机制

近似最近邻检索需要显式 Graph Layer、Neighbor Bound、Entry Point、Traversal Budget 与 Tie Rule。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

Graph 构建与搜索可复现，绝不返回已删除、重复或越界 Candidate。

### 机制板块

#### 确定性 HNSW 搜索机制

Graph 构建与搜索可复现，绝不返回已删除、重复或越界 Candidate。

??? note "文件差异：src/miniqdrant/index/hnsw.py"
    ```diff
    diff --git a/src/miniqdrant/index/hnsw.py b/src/miniqdrant/index/hnsw.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..e77782e4b3edf44bff6d3943b039f59cca92c160
    --- /dev/null
    +++ b/src/miniqdrant/index/hnsw.py
    @@ -0,0 +1,292 @@
    +from __future__ import annotations
    +
    +import hashlib
    +import heapq
    +from collections.abc import Iterable, Set
    +from dataclasses import dataclass
    +
    +from miniqdrant.config import Distance, HnswConfig
    +from miniqdrant.ids import PointId, point_id_bytes, point_id_sort_key
    +from miniqdrant.metrics import score
    +from miniqdrant.models import StoredPoint, Vector, normalize_cosine, validate_vector
    +from miniqdrant.segment.base import ScoredCandidate
    +from miniqdrant.topk import TopK
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class HnswGraph:
    +    entry_point: PointId | None
    +    max_level: int
    +    levels: dict[PointId, int]
    +    layers: dict[int, dict[PointId, tuple[PointId, ...]]]
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class HnswSearchResult:
    +    candidates: tuple[ScoredCandidate, ...]
    +    visited_count: int
    +
    +
    +class HnswIndex:
    +    def __init__(
    +        self,
    +        distance: Distance,
    +        config: HnswConfig,
    +        points: Iterable[StoredPoint],
    +    ) -> None:
    +        self._distance = distance
    +        self._config = config
    +        ordered = sorted(points, key=lambda point: point_id_sort_key(point.id))
    +        self._vectors = {point.id: point.vector for point in ordered}
    +        self._versions = {point.id: point.version for point in ordered}
    +        self._dimension = len(ordered[0].vector) if ordered else 0
    +        self._levels: dict[PointId, int] = {}
    +        self._layers: dict[int, dict[PointId, set[PointId]]] = {}
    +        self._deleted: set[PointId] = {
    +            point.id for point in ordered if point.deleted
    +        }
    +        self._entry_point: PointId | None = None
    +        self._max_level = -1
    +        for point in ordered:
    +            self._insert(point.id)
    +
    +    @classmethod
    +    def build(
    +        cls,
    +        points: Iterable[StoredPoint],
    +        *,
    +        distance: Distance,
    +        config: HnswConfig,
    +    ) -> HnswIndex:
    +        return cls(distance, config, points)
    +
    +    def mark_deleted(self, point_id: PointId) -> None:
    +        if point_id in self._vectors:
    +            self._deleted.add(point_id)
    +
    +    def export_graph(self) -> HnswGraph:
    +        return HnswGraph(
    +            entry_point=self._entry_point,
    +            max_level=self._max_level,
    +            levels=dict(self._levels),
    +            layers={
    +                layer: {
    +                    point_id: tuple(sorted(neighbors, key=point_id_sort_key))
    +                    for point_id, neighbors in sorted(
    +                        adjacency.items(),
    +                        key=lambda item: point_id_sort_key(item[0]),
    +                    )
    +                }
    +                for layer, adjacency in sorted(self._layers.items())
    +            },
    +        )
    +
    +    def search(
    +        self,
    +        query: Vector,
    +        *,
    +        limit: int,
    +        ef_search: int | None = None,
    +        allowed_ids: Set[PointId] | None = None,
    +    ) -> HnswSearchResult:
    +        if limit < 1:
    +            raise ValueError("search limit must be positive")
    +        if self._entry_point is None:
    +            return HnswSearchResult((), 0)
    +        normalized = validate_vector(query, self._dimension)
    +        if self._distance is Distance.COSINE:
    +            normalized = normalize_cosine(normalized)
    +        breadth = max(limit, ef_search or self._config.ef_search)
    +        entry = self._entry_point
    +        visited: set[PointId] = {entry}
    +        for layer in range(self._max_level, 0, -1):
    +            entry, layer_visited = self._greedy(normalized, entry, layer)
    +            visited.update(layer_visited)
    +        scores, layer_visited = self._search_layer(normalized, (entry,), breadth, 0)
    +        visited.update(layer_visited)
    +        while len(scores) < breadth and len(visited) < len(self._vectors):
    +            next_entry = min(
    +                self._vectors.keys() - visited,
    +                key=point_id_sort_key,
    +            )
    +            additional_scores, additional_visited = self._search_layer(
    +                normalized,
    +                (next_entry,),
    +                breadth,
    +                0,
    +            )
    +            scores.update(additional_scores)
    +            visited.update(additional_visited)
    +        collector = TopK(limit)
    +        for point_id, point_score in scores.items():
    +            if point_id in self._deleted:
    +                continue
    +            if allowed_ids is not None and point_id not in allowed_ids:
    +                continue
    +            collector.offer(point_id, point_score)
    +        candidates = tuple(
    +            ScoredCandidate(item.point_id, item.score, self._versions[item.point_id])
    +            for item in collector.results()
    +        )
    +        return HnswSearchResult(candidates, len(visited))
    +
    +    def _insert(self, point_id: PointId) -> None:
    +        level = _deterministic_level(point_id, self._config.seed)
    +        self._levels[point_id] = level
    +        for layer in range(level + 1):
    +            self._layers.setdefault(layer, {})[point_id] = set()
    +        if self._entry_point is None:
    +            self._entry_point = point_id
    +            self._max_level = level
    +            return
    +
    +        entry = self._entry_point
    +        vector = self._vectors[point_id]
    +        for layer in range(self._max_level, level, -1):
    +            entry, _ = self._greedy(vector, entry, layer)
    +        for layer in range(min(level, self._max_level), -1, -1):
    +            scores, _ = self._search_layer(
    +                vector,
    +                (entry,),
    +                self._config.ef_construct,
    +                layer,
    +            )
    +            neighbors = [
    +                candidate_id
    +                for candidate_id, _ in sorted(
    +                    scores.items(),
    +                    key=lambda item: (-item[1], point_id_sort_key(item[0])),
    +                )
    +                if candidate_id != point_id
    +            ][: self._config.m]
    +            for neighbor in neighbors:
    +                self._layers[layer][point_id].add(neighbor)
    +                self._layers[layer][neighbor].add(point_id)
    +                self._prune(neighbor, layer)
    +            self._prune(point_id, layer)
    +            if neighbors:
    +                entry = neighbors[0]
    +        if level > self._max_level:
    +            self._entry_point = point_id
    +            self._max_level = level
    +
    +    def _greedy(
    +        self,
    +        query: Vector,
    +        entry: PointId,
    +        layer: int,
    +    ) -> tuple[PointId, set[PointId]]:
    +        current = entry
    +        current_score = score(self._distance, query, self._vectors[current])
    +        visited = {current}
    +        changed = True
    +        while changed:
    +            changed = False
    +            for neighbor in self._layers.get(layer, {}).get(current, ()):
    +                visited.add(neighbor)
    +                neighbor_score = score(self._distance, query, self._vectors[neighbor])
    +                if _better(neighbor, neighbor_score, current, current_score):
    +                    current = neighbor
    +                    current_score = neighbor_score
    +                    changed = True
    +        return current, visited
    +
    +    def _search_layer(
    +        self,
    +        query: Vector,
    +        entries: Iterable[PointId],
    +        breadth: int,
    +        layer: int,
    +    ) -> tuple[dict[PointId, float], set[PointId]]:
    +        visited: set[PointId] = set()
    +        scores: dict[PointId, float] = {}
    +        frontier: list[tuple[float, tuple[int, int], PointId]] = []
    +        best: list[PointId] = []
    +        for entry in entries:
    +            if entry in visited:
    +                continue
    +            visited.add(entry)
    +            entry_score = score(self._distance, query, self._vectors[entry])
    +            scores[entry] = entry_score
    +            heapq.heappush(
    +                frontier,
    +                (-entry_score, point_id_sort_key(entry), entry),
    +            )
    +            best.append(entry)
    +
    +        while frontier:
    +            negative_score, _, current = heapq.heappop(frontier)
    +            current_score = -negative_score
    +            best = _best_ids(best, scores, breadth)
    +            if len(best) >= breadth and current_score < scores[best[-1]]:
    +                break
    +            for neighbor in self._layers.get(layer, {}).get(current, ()):
    +                if neighbor in visited:
    +                    continue
    +                visited.add(neighbor)
    +                neighbor_score = score(self._distance, query, self._vectors[neighbor])
    +                scores[neighbor] = neighbor_score
    +                best = _best_ids([*best, neighbor], scores, breadth)
    +                if neighbor in best:
    +                    heapq.heappush(
    +                        frontier,
    +                        (-neighbor_score, point_id_sort_key(neighbor), neighbor),
    +                    )
    +        return {point_id: scores[point_id] for point_id in best}, visited
    +
    +    def _prune(self, point_id: PointId, layer: int) -> None:
    +        neighbors = self._layers[layer][point_id]
    +        if len(neighbors) <= self._config.m:
    +            return
    +        retained = set(
    +            sorted(
    +                neighbors,
    +                key=lambda neighbor: (
    +                    -score(
    +                        self._distance,
    +                        self._vectors[point_id],
    +                        self._vectors[neighbor],
    +                    ),
    +                    point_id_sort_key(neighbor),
    +                ),
    +            )[: self._config.m]
    +        )
    +        removed = neighbors.difference(retained)
    +        self._layers[layer][point_id] = retained
    +        for neighbor in removed:
    +            self._layers[layer][neighbor].discard(point_id)
    +
    +
    +def _deterministic_level(point_id: PointId, seed: int, maximum: int = 16) -> int:
    +    digest = hashlib.blake2b(
    +        seed.to_bytes(8, "big", signed=True) + point_id_bytes(point_id),
    +        digest_size=8,
    +    ).digest()
    +    bits = int.from_bytes(digest, "big")
    +    level = 0
    +    while level < maximum and bits & 1:
    +        level += 1
    +        bits >>= 1
    +    return level
    +
    +
    +def _best_ids(
    +    point_ids: Iterable[PointId],
    +    scores: dict[PointId, float],
    +    breadth: int,
    +) -> list[PointId]:
    +    return sorted(
    +        set(point_ids),
    +        key=lambda point_id: (-scores[point_id], point_id_sort_key(point_id)),
    +    )[:breadth]
    +
    +
    +def _better(
    +    left_id: PointId,
    +    left_score: float,
    +    right_id: PointId,
    +    right_score: float,
    +) -> bool:
    +    if left_score != right_score:
    +        return left_score > right_score
    +    return point_id_sort_key(left_id) < point_id_sort_key(right_id)
    ```

**是什么，为什么现在需要**

核心机制是确定性 HNSW 搜索。近似最近邻检索需要显式 Graph Layer、Neighbor Bound、Entry Point、Traversal Budget 与 Tie Rule。

**在运行时做什么**

Graph 构建与搜索可复现，绝不返回已删除、重复或越界 Candidate。

**关键语句理解**

真正要守住的边界是：Graph 构建与搜索可复现，绝不返回已删除、重复或越界 Candidate。

#### 包、Fixture 与工程支撑

保持包导出、测试语料、依赖与运行环境可复现。

??? note "支撑文件差异（1 个文件）"
    **`src/miniqdrant/index/__init__.py`**

    ```diff
    diff --git a/src/miniqdrant/index/__init__.py b/src/miniqdrant/index/__init__.py
    index 6258a2e6c9801284328037ba58744bfda1821b42..f44f9cc27ccd82680b2e38a9b8eede0795bc01da 100644
    --- a/src/miniqdrant/index/__init__.py
    +++ b/src/miniqdrant/index/__init__.py
    @@ -1,4 +1,4 @@
    +from miniqdrant.index.hnsw import HnswGraph, HnswIndex, HnswSearchResult
     from miniqdrant.index.plain import PlainVectorIndex

    -__all__ = ["PlainVectorIndex"]
    -
    +__all__ = ["HnswGraph", "HnswIndex", "HnswSearchResult", "PlainVectorIndex"]
    ```


### 验证证据

运行 `uv run pytest -q $(cat journey/stages/07-hnsw-search/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：Graph 构建与搜索可复现，绝不返回已删除、重复或越界 Candidate。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 5 章](https://github.com/system-in-miniature/mini-qdrant/blob/main/docs/zh/tutorial/05-hnsw.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-qdrant/blob/main/journey/stages/07-hnsw-search/stage.patch)
