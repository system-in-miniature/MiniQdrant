# Stage 06 · 过滤感知查询规划

### 目标

实现过滤感知查询规划，并能从可执行反例、运行时状态与关键语句解释其边界。

??? note "交付文件"
    - `src/miniqdrant/__init__.py`
    - `src/miniqdrant/collection.py`
    - `src/miniqdrant/filters/__init__.py`
    - `src/miniqdrant/filters/cardinality.py`
    - `src/miniqdrant/filters/index.py`
    - `src/miniqdrant/query/__init__.py`
    - `src/miniqdrant/query/executor.py`
    - `src/miniqdrant/query/planner.py`
    - `src/miniqdrant/segment/mutable.py`
    - `tests/query/test_payload_index.py`
    - `tests/query/test_plan_parity.py`
    - `tests/query/test_planner.py`

### 当前遇到的问题

精确扫描、Payload Index 与 Filter 需要 Planner 选择 Candidate，同时不得改变结果语义。

### 测试契约

#### 先看会坏在哪里

聚焦测试让过滤感知查询规划经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

??? note "文件差异：tests/query/test_payload_index.py"
    ```diff
    diff --git a/tests/query/test_payload_index.py b/tests/query/test_payload_index.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..c5c3e8d1fc505350c678c922b1dde28d1ab6489e
    --- /dev/null
    +++ b/tests/query/test_payload_index.py
    @@ -0,0 +1,72 @@
    +from __future__ import annotations
    +
    +from miniqdrant.config import CollectionConfig, Distance
    +from miniqdrant.filters import Filter, Match, Range, matches_filter
    +from miniqdrant.filters.index import PayloadIndexSet, PayloadSchema
    +from miniqdrant.models import Point, validate_point
    +
    +
    +def points():
    +    config = CollectionConfig(dimension=2, distance=Distance.DOT)
    +    return tuple(
    +        validate_point(point, config)
    +        for point in (
    +            Point(1, (1, 0), {"kind": "book", "price": 10.0}),
    +            Point(2, (0, 1), {"kind": "movie", "price": 20.0}),
    +            Point(3, (1, 1), {"kind": "book", "price": 30.0}),
    +        )
    +    )
    +
    +
    +def test_payload_index_candidates_equal_scan() -> None:
    +    stored = points()
    +    indexes = PayloadIndexSet(record.id for record in stored)
    +    indexes.create("kind", PayloadSchema.KEYWORD, stored)
    +    indexes.create("price", PayloadSchema.FLOAT, stored)
    +    condition = Filter(
    +        must=(Match("kind", "book"), Range("price", lte=20.0)),
    +    )
    +
    +    indexed = indexes.candidates(condition)
    +    scanned = {
    +        point.id
    +        for point in stored
    +        if matches_filter(point.id, point.payload, condition)
    +    }
    +
    +    assert indexed.exact
    +    assert indexed.ids == scanned == {1}
    +    assert indexed.estimate.minimum == 1
    +    assert indexed.estimate.maximum == 1
    +
    +
    +def test_unindexed_condition_is_retained_as_residual() -> None:
    +    stored = points()
    +    indexes = PayloadIndexSet(record.id for record in stored)
    +    indexes.create("kind", PayloadSchema.KEYWORD, stored)
    +    condition = Filter(
    +        must=(Match("kind", "book"), Range("price", lte=20.0)),
    +    )
    +
    +    candidates = indexes.candidates(condition)
    +
    +    assert not candidates.exact
    +    assert candidates.ids == {1, 3}
    +    assert candidates.residual is condition
    +    assert candidates.estimate.maximum == 2
    +
    +
    +def test_index_update_removes_old_value() -> None:
    +    stored = points()
    +    indexes = PayloadIndexSet(record.id for record in stored)
    +    indexes.create("kind", PayloadSchema.KEYWORD, stored)
    +    replacement = validate_point(
    +        Point(1, (1, 0), {"kind": "movie", "price": 10.0}),
    +        CollectionConfig(dimension=2, distance=Distance.DOT),
    +    )
    +
    +    indexes.upsert(replacement)
    +
    +    books = indexes.candidates(Filter(must=(Match("kind", "book"),)))
    +    assert books.ids == {3}
    +
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让过滤感知查询规划经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert identifiers is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/query/test_plan_parity.py"
    ```diff
    diff --git a/tests/query/test_plan_parity.py b/tests/query/test_plan_parity.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..e998b596c170ae921731f6f5bf19decbe6b2e789
    --- /dev/null
    +++ b/tests/query/test_plan_parity.py
    @@ -0,0 +1,27 @@
    +from __future__ import annotations
    +
    +from miniqdrant import Database, Distance, Filter, Match, Point, SearchRequest
    +from miniqdrant.filters.index import PayloadSchema
    +
    +
    +def test_indexed_and_unindexed_exact_search_return_same_hits(tmp_path) -> None:
    +    database = Database.open(tmp_path)
    +    plain = database.create_collection("plain", dimension=2, distance=Distance.DOT)
    +    indexed = database.create_collection("indexed", dimension=2, distance=Distance.DOT)
    +    points = [
    +        Point(1, (1.0, 0.0), {"kind": "book"}),
    +        Point(2, (0.9, 0.1), {"kind": "movie"}),
    +        Point(3, (0.8, 0.2), {"kind": "book"}),
    +    ]
    +    plain.upsert(points)
    +    indexed.upsert(points)
    +    indexed.create_payload_index("kind", PayloadSchema.KEYWORD)
    +    request = SearchRequest(
    +        (1.0, 0.0),
    +        10,
    +        filter=Filter(must=(Match("kind", "book"),)),
    +        exact=True,
    +    )
    +
    +    assert indexed.search(request).hits == plain.search(request).hits
    +
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让过滤感知查询规划经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert identifiers is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/query/test_planner.py"
    ```diff
    diff --git a/tests/query/test_planner.py b/tests/query/test_planner.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..bfebee6738d91e9548bf686cadb5d746c7a151d2
    --- /dev/null
    +++ b/tests/query/test_planner.py
    @@ -0,0 +1,49 @@
    +from __future__ import annotations
    +
    +import pytest
    +
    +from miniqdrant.filters.cardinality import CardinalityEstimate
    +from miniqdrant.query.planner import QueryPlanner, SegmentFacts, Strategy
    +
    +
    +@pytest.mark.parametrize(
    +    ("facts", "expected"),
    +    [
    +        (SegmentFacts(total_points=10), Strategy.EXACT_FULL_SCAN),
    +        (
    +            SegmentFacts(
    +                total_points=10_000,
    +                filtered=CardinalityEstimate.exact_count(5),
    +            ),
    +            Strategy.FILTER_THEN_EXACT,
    +        ),
    +        (
    +            SegmentFacts(
    +                total_points=10_000,
    +                filtered=CardinalityEstimate(0, 4_000, 8_000, False),
    +            ),
    +            Strategy.FILTERED_HNSW,
    +        ),
    +        (SegmentFacts(total_points=10_000), Strategy.HNSW),
    +        (
    +            SegmentFacts(total_points=10_000, has_quantization=True),
    +            Strategy.QUANTIZED_HNSW_RESCORE,
    +        ),
    +        (
    +            SegmentFacts(total_points=10_000, exact_requested=True),
    +            Strategy.EXACT_FULL_SCAN,
    +        ),
    +    ],
    +)
    +def test_planner_boundaries(facts, expected) -> None:
    +    plan = QueryPlanner(plain_threshold=100, filter_scan_threshold=100).choose(facts)
    +    assert plan.strategy is expected
    +
    +
    +def test_plan_is_inspectable() -> None:
    +    plan = QueryPlanner(plain_threshold=100, filter_scan_threshold=100).choose(
    +        SegmentFacts(total_points=10)
    +    )
    +
    +    assert plan.reason == "segment below plain-scan threshold"
    +    assert plan.total_points == 10
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让过滤感知查询规划经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert identifiers is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是过滤感知查询规划。精确扫描、Payload Index 与 Filter 需要 Planner 选择 Candidate，同时不得改变结果语义。

### 为什么需要这个机制

精确扫描、Payload Index 与 Filter 需要 Planner 选择 Candidate，同时不得改变结果语义。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

Plan 可以缩小 Candidate，但执行始终保持与参考扫描相同的 Filter 和精确分数语义。

### 机制板块

#### 过滤感知查询规划机制

Plan 可以缩小 Candidate，但执行始终保持与参考扫描相同的 Filter 和精确分数语义。

??? note "文件差异：src/miniqdrant/collection.py"
    ```diff
    diff --git a/src/miniqdrant/collection.py b/src/miniqdrant/collection.py
    index 59c6856a31775b00db453df146a1a651ae28e4a8..f4fb5b1bbb6d272db8052cbfb0c52227af8932c2 100644
    --- a/src/miniqdrant/collection.py
    +++ b/src/miniqdrant/collection.py
    @@ -8,6 +8,7 @@ from threading import RLock
     from miniqdrant.config import CollectionConfig
     from miniqdrant.errors import InvalidFilterError
     from miniqdrant.filters import Filter
    +from miniqdrant.filters.index import PayloadSchema
     from miniqdrant.ids import PointId, canonicalize_point_id
     from miniqdrant.lifecycle import Lifecycle
     from miniqdrant.models import (
    @@ -72,6 +73,11 @@ class Collection(Lifecycle):
                     self._mutable.apply_delete(point_id, version)
                 return version

    +    def create_payload_index(self, path: str, schema: PayloadSchema | str) -> None:
    +        self._ensure_open()
    +        with self._update_lock:
    +            self._mutable.create_payload_index(path, PayloadSchema(schema))
    +
         def retrieve(self, point_ids: Iterable[object]) -> tuple[StoredPoint, ...]:
             self._ensure_open()
             identifiers = tuple(canonicalize_point_id(item) for item in point_ids)
    @@ -140,4 +146,3 @@ class Collection(Lifecycle):
                 payload=point.payload if request.with_payload else None,
                 vector=point.vector if request.with_vector else None,
             )
    -
    ```

??? note "文件差异：src/miniqdrant/filters/cardinality.py"
    ```diff
    diff --git a/src/miniqdrant/filters/cardinality.py b/src/miniqdrant/filters/cardinality.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..ff835a1f07c06864e9a22e387eb28e947336c537
    --- /dev/null
    +++ b/src/miniqdrant/filters/cardinality.py
    @@ -0,0 +1,22 @@
    +from __future__ import annotations
    +
    +from dataclasses import dataclass
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class CardinalityEstimate:
    +    minimum: int
    +    expected: int
    +    maximum: int
    +    exact: bool
    +
    +    def __post_init__(self) -> None:
    +        if not 0 <= self.minimum <= self.expected <= self.maximum:
    +            raise ValueError("cardinality bounds must be ordered and non-negative")
    +        if self.exact and not self.minimum == self.expected == self.maximum:
    +            raise ValueError("exact cardinality must have equal bounds")
    +
    +    @classmethod
    +    def exact_count(cls, count: int) -> CardinalityEstimate:
    +        return cls(count, count, count, True)
    +
    ```

??? note "文件差异：src/miniqdrant/filters/index.py"
    ```diff
    diff --git a/src/miniqdrant/filters/index.py b/src/miniqdrant/filters/index.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..fa3d2af741a35ce02b7ed32ebcd8edd3f69f61c7
    --- /dev/null
    +++ b/src/miniqdrant/filters/index.py
    @@ -0,0 +1,189 @@
    +from __future__ import annotations
    +
    +import math
    +from collections import defaultdict
    +from collections.abc import Iterable
    +from dataclasses import dataclass
    +from enum import StrEnum
    +from numbers import Real
    +
    +from miniqdrant.filters.ast import Condition, Filter, HasId, Match, Range
    +from miniqdrant.filters.cardinality import CardinalityEstimate
    +from miniqdrant.filters.evaluate import resolve_path
    +from miniqdrant.ids import PointId
    +from miniqdrant.models import StoredPoint
    +
    +
    +class PayloadSchema(StrEnum):
    +    KEYWORD = "keyword"
    +    INTEGER = "integer"
    +    FLOAT = "float"
    +    BOOL = "bool"
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class CandidateSet:
    +    ids: frozenset[PointId]
    +    estimate: CardinalityEstimate
    +    exact: bool
    +    residual: Filter | None
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class _Resolved:
    +    ids: frozenset[PointId]
    +    exact: bool
    +
    +
    +class PayloadFieldIndex:
    +    def __init__(self, path: str, schema: PayloadSchema) -> None:
    +        self.path = path
    +        self.schema = PayloadSchema(schema)
    +        self._values_by_id: dict[PointId, tuple[object, ...]] = {}
    +        self._equals: dict[object, set[PointId]] = defaultdict(set)
    +
    +    def upsert(self, point: StoredPoint) -> None:
    +        self.delete(point.id)
    +        values = tuple(
    +            value
    +            for value in resolve_path(point.payload, self.path)
    +            if self._accepts(value)
    +        )
    +        self._values_by_id[point.id] = values
    +        for value in values:
    +            self._equals[value].add(point.id)
    +
    +    def delete(self, point_id: PointId) -> None:
    +        for value in self._values_by_id.pop(point_id, ()):
    +            identifiers = self._equals[value]
    +            identifiers.discard(point_id)
    +            if not identifiers:
    +                del self._equals[value]
    +
    +    def match(self, value: object) -> frozenset[PointId] | None:
    +        if not self._accepts(value):
    +            return frozenset()
    +        return frozenset(self._equals.get(value, ()))
    +
    +    def range(self, condition: Range) -> frozenset[PointId] | None:
    +        if self.schema not in (PayloadSchema.INTEGER, PayloadSchema.FLOAT):
    +            return None
    +        return frozenset(
    +            point_id
    +            for point_id, values in self._values_by_id.items()
    +            if any(_in_range(value, condition) for value in values)
    +        )
    +
    +    def _accepts(self, value: object) -> bool:
    +        if self.schema is PayloadSchema.KEYWORD:
    +            return isinstance(value, str)
    +        if self.schema is PayloadSchema.BOOL:
    +            return isinstance(value, bool)
    +        if self.schema is PayloadSchema.INTEGER:
    +            return isinstance(value, int) and not isinstance(value, bool)
    +        return (
    +            isinstance(value, Real)
    +            and not isinstance(value, bool)
    +            and math.isfinite(float(value))
    +        )
    +
    +
    +class PayloadIndexSet:
    +    def __init__(self, live_ids: Iterable[PointId] = ()) -> None:
    +        self._live_ids = set(live_ids)
    +        self._indexes: dict[str, PayloadFieldIndex] = {}
    +
    +    @property
    +    def schemas(self) -> dict[str, PayloadSchema]:
    +        return {path: index.schema for path, index in self._indexes.items()}
    +
    +    def create(
    +        self,
    +        path: str,
    +        schema: PayloadSchema,
    +        points: Iterable[StoredPoint],
    +    ) -> None:
    +        index = PayloadFieldIndex(path, schema)
    +        for point in points:
    +            if not point.deleted:
    +                index.upsert(point)
    +                self._live_ids.add(point.id)
    +        self._indexes[path] = index
    +
    +    def upsert(self, point: StoredPoint) -> None:
    +        self._live_ids.add(point.id)
    +        for index in self._indexes.values():
    +            index.upsert(point)
    +
    +    def delete(self, point_id: PointId) -> None:
    +        self._live_ids.discard(point_id)
    +        for index in self._indexes.values():
    +            index.delete(point_id)
    +
    +    def candidates(self, filter_: Filter | None) -> CandidateSet:
    +        universe = frozenset(self._live_ids)
    +        if filter_ is None:
    +            estimate = CardinalityEstimate.exact_count(len(universe))
    +            return CandidateSet(universe, estimate, True, None)
    +        resolved = self._resolve(filter_, universe)
    +        if resolved.exact:
    +            estimate = CardinalityEstimate.exact_count(len(resolved.ids))
    +            return CandidateSet(resolved.ids, estimate, True, None)
    +        estimate = CardinalityEstimate(0, len(resolved.ids) // 2, len(resolved.ids), False)
    +        return CandidateSet(resolved.ids, estimate, False, filter_)
    +
    +    def _resolve(self, condition: Condition, universe: frozenset[PointId]) -> _Resolved:
    +        if isinstance(condition, HasId):
    +            return _Resolved(universe.intersection(condition.ids), True)
    +        if isinstance(condition, Match):
    +            index = self._indexes.get(condition.path)
    +            if index is None:
    +                return _Resolved(universe, False)
    +            identifiers = index.match(condition.value)
    +            assert identifiers is not None
    +            return _Resolved(universe.intersection(identifiers), True)
    +        if isinstance(condition, Range):
    +            index = self._indexes.get(condition.path)
    +            if index is None:
    +                return _Resolved(universe, False)
    +            identifiers = index.range(condition)
    +            if identifiers is None:
    +                return _Resolved(universe, False)
    +            return _Resolved(universe.intersection(identifiers), True)
    +        return self._resolve_filter(condition, universe)
    +
    +    def _resolve_filter(self, filter_: Filter, universe: frozenset[PointId]) -> _Resolved:
    +        current = universe
    +        exact = True
    +        for condition in filter_.must:
    +            resolved = self._resolve(condition, universe)
    +            current = current.intersection(resolved.ids)
    +            exact = exact and resolved.exact
    +        if filter_.should:
    +            resolved_should = tuple(
    +                self._resolve(condition, universe) for condition in filter_.should
    +            )
    +            if all(item.exact for item in resolved_should):
    +                allowed = frozenset().union(*(item.ids for item in resolved_should))
    +                current = current.intersection(allowed)
    +            else:
    +                exact = False
    +        for condition in filter_.must_not:
    +            resolved = self._resolve(condition, universe)
    +            if resolved.exact:
    +                current = current.difference(resolved.ids)
    +            else:
    +                exact = False
    +        return _Resolved(frozenset(current), exact)
    +
    +
    +def _in_range(value: object, condition: Range) -> bool:
    +    if isinstance(value, bool) or not isinstance(value, Real):
    +        return False
    +    if condition.gt is not None and value <= condition.gt:
    +        return False
    +    if condition.gte is not None and value < condition.gte:
    +        return False
    +    if condition.lt is not None and value >= condition.lt:
    +        return False
    +    return condition.lte is None or value <= condition.lte
    ```

??? note "文件差异：src/miniqdrant/query/executor.py"
    ```diff
    diff --git a/src/miniqdrant/query/executor.py b/src/miniqdrant/query/executor.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..7a3c9be82219bbaf1a5b591a9bbe99d0dbfe7a22
    --- /dev/null
    +++ b/src/miniqdrant/query/executor.py
    @@ -0,0 +1,6 @@
    +from __future__ import annotations
    +
    +from miniqdrant.query.planner import QueryPlanner, SearchPlan, SegmentFacts, Strategy
    +
    +__all__ = ["QueryPlanner", "SearchPlan", "SegmentFacts", "Strategy"]
    +
    ```

??? note "文件差异：src/miniqdrant/query/planner.py"
    ```diff
    diff --git a/src/miniqdrant/query/planner.py b/src/miniqdrant/query/planner.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..5377c75e88f656eb30d7a5cfcf3d34e1731c10fb
    --- /dev/null
    +++ b/src/miniqdrant/query/planner.py
    @@ -0,0 +1,76 @@
    +from __future__ import annotations
    +
    +from dataclasses import dataclass
    +from enum import StrEnum
    +
    +from miniqdrant.filters.cardinality import CardinalityEstimate
    +
    +
    +class Strategy(StrEnum):
    +    EXACT_FULL_SCAN = "exact_full_scan"
    +    FILTER_THEN_EXACT = "filter_then_exact"
    +    HNSW = "hnsw"
    +    FILTERED_HNSW = "filtered_hnsw"
    +    QUANTIZED_HNSW_RESCORE = "quantized_hnsw_rescore"
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class SegmentFacts:
    +    total_points: int
    +    filtered: CardinalityEstimate | None = None
    +    has_hnsw: bool = True
    +    has_quantization: bool = False
    +    exact_requested: bool = False
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class SearchPlan:
    +    strategy: Strategy
    +    reason: str
    +    total_points: int
    +    filtered: CardinalityEstimate | None
    +
    +
    +class QueryPlanner:
    +    def __init__(self, plain_threshold: int, filter_scan_threshold: int) -> None:
    +        if plain_threshold < 0 or filter_scan_threshold < 0:
    +            raise ValueError("planner thresholds must be non-negative")
    +        self._plain_threshold = plain_threshold
    +        self._filter_scan_threshold = filter_scan_threshold
    +
    +    def choose(self, facts: SegmentFacts) -> SearchPlan:
    +        if facts.exact_requested:
    +            return self._plan(Strategy.EXACT_FULL_SCAN, "exact search requested", facts)
    +        if facts.total_points <= self._plain_threshold or not facts.has_hnsw:
    +            return self._plan(
    +                Strategy.EXACT_FULL_SCAN,
    +                "segment below plain-scan threshold",
    +                facts,
    +            )
    +        if (
    +            facts.filtered is not None
    +            and facts.filtered.maximum <= self._filter_scan_threshold
    +        ):
    +            return self._plan(
    +                Strategy.FILTER_THEN_EXACT,
    +                "indexed filter candidates below exact threshold",
    +                facts,
    +            )
    +        if facts.has_quantization:
    +            return self._plan(
    +                Strategy.QUANTIZED_HNSW_RESCORE,
    +                "quantized index available for approximate search",
    +                facts,
    +            )
    +        if facts.filtered is not None:
    +            return self._plan(
    +                Strategy.FILTERED_HNSW,
    +                "filtered population remains above exact threshold",
    +                facts,
    +            )
    +        return self._plan(Strategy.HNSW, "large unfiltered segment", facts)
    +
    +    @staticmethod
    +    def _plan(strategy: Strategy, reason: str, facts: SegmentFacts) -> SearchPlan:
    +        return SearchPlan(strategy, reason, facts.total_points, facts.filtered)
    +
    ```

??? note "文件差异：src/miniqdrant/segment/mutable.py"
    ```diff
    diff --git a/src/miniqdrant/segment/mutable.py b/src/miniqdrant/segment/mutable.py
    index 979fb8314bb269acd6c7f96b5287c01548f3c775..98bbbb5905eaaf494572bc85b947afd0c70cd407 100644
    --- a/src/miniqdrant/segment/mutable.py
    +++ b/src/miniqdrant/segment/mutable.py
    @@ -3,6 +3,7 @@ from __future__ import annotations
     from dataclasses import replace

     from miniqdrant.config import CollectionConfig, Distance
    +from miniqdrant.filters.index import PayloadIndexSet, PayloadSchema
     from miniqdrant.ids import PointId, canonicalize_point_id
     from miniqdrant.index.plain import PlainVectorIndex
     from miniqdrant.json_values import freeze_json_object
    @@ -14,6 +15,11 @@ class MutableSegment:
         def __init__(self, config: CollectionConfig) -> None:
             self._config = config
             self._records: dict[PointId, StoredPoint] = {}
    +        self._payload_indexes = PayloadIndexSet()
    +
    +    @property
    +    def payload_indexes(self) -> PayloadIndexSet:
    +        return self._payload_indexes

         @property
         def live_count(self) -> int:
    @@ -39,6 +45,9 @@ class MutableSegment:
         def iter_records(self) -> tuple[StoredPoint, ...]:
             return tuple(self._records.values())

    +    def create_payload_index(self, path: str, schema: PayloadSchema) -> None:
    +        self._payload_indexes.create(path, schema, self.iter_live())
    +
         def apply_upsert(self, point: Point, version: int) -> bool:
             if version < 1:
                 raise ValueError("point version must be positive")
    @@ -46,7 +55,9 @@ class MutableSegment:
             current = self._records.get(validated.id)
             if current is not None and current.version >= version:
                 return False
    -        self._records[validated.id] = replace(validated, version=version)
    +        stored = replace(validated, version=version)
    +        self._records[validated.id] = stored
    +        self._payload_indexes.upsert(stored)
             return True

         def apply_delete(self, point_id: object, version: int) -> bool:
    @@ -63,12 +74,16 @@ class MutableSegment:
                 version=version,
                 deleted=True,
             )
    +        self._payload_indexes.delete(canonical)
             return True

         def search(self, request: SegmentSearchRequest) -> SegmentSearchResult:
             query = validate_vector(request.vector, self._config.dimension)
             if self._config.distance is Distance.COSINE:
                 query = normalize_cosine(query)
    -        index = PlainVectorIndex(self._config.distance, self.iter_live())
    -        return index.search_with_stats(query, request.limit, request.filter)
    -
    +        candidate_set = self._payload_indexes.candidates(request.filter)
    +        points = tuple(
    +            point for point in self.iter_live() if point.id in candidate_set.ids
    +        )
    +        index = PlainVectorIndex(self._config.distance, points)
    +        return index.search_with_stats(query, request.limit, candidate_set.residual)
    ```

**是什么，为什么现在需要**

核心机制是过滤感知查询规划。精确扫描、Payload Index 与 Filter 需要 Planner 选择 Candidate，同时不得改变结果语义。

**在运行时做什么**

Plan 可以缩小 Candidate，但执行始终保持与参考扫描相同的 Filter 和精确分数语义。

**关键语句理解**

真正要守住的边界是：Plan 可以缩小 Candidate，但执行始终保持与参考扫描相同的 Filter 和精确分数语义。

#### 包、Fixture 与工程支撑

保持包导出、测试语料、依赖与运行环境可复现。

??? note "支撑文件差异（3 个文件）"
    **`src/miniqdrant/__init__.py`**

    ```diff
    diff --git a/src/miniqdrant/__init__.py b/src/miniqdrant/__init__.py
    index d57fe02bd682ba9f35a31eb162cd2aaeeb9f84db..d6ac8d3b970a3a1d0d69a0501b7b10e82dd28bbc 100644
    --- a/src/miniqdrant/__init__.py
    +++ b/src/miniqdrant/__init__.py
    @@ -20,13 +20,22 @@ from miniqdrant.errors import (
         SchemaMismatchError,
         SnapshotError,
     )
    -from miniqdrant.filters import Filter, HasId, Match, Range, matches_filter
    +from miniqdrant.filters import (
    +    CardinalityEstimate,
    +    Filter,
    +    HasId,
    +    Match,
    +    PayloadSchema,
    +    Range,
    +    matches_filter,
    +)
     from miniqdrant.models import Point, SearchHit, SearchRequest, SearchResult, StoredPoint
     from miniqdrant.segment import MutableSegment, SegmentSearchRequest
     from miniqdrant.topk import Candidate, TopK

     __all__ = [
         "Candidate",
    +    "CardinalityEstimate",
         "ClosedResourceError",
         "Collection",
         "CollectionConfig",
    @@ -46,6 +55,7 @@ __all__ = [
         "MutableSegment",
         "OptimizerConfig",
         "PayloadIndexError",
    +    "PayloadSchema",
         "Point",
         "Range",
         "ScalarQuantizationConfig",
    ```

    **`src/miniqdrant/filters/__init__.py`**

    ```diff
    diff --git a/src/miniqdrant/filters/__init__.py b/src/miniqdrant/filters/__init__.py
    index aa71632273b06faa5ab4f811f672f7e114397838..baaf6ee8ed37fd2500317ecf83e9b37019f741cc 100644
    --- a/src/miniqdrant/filters/__init__.py
    +++ b/src/miniqdrant/filters/__init__.py
    @@ -1,14 +1,19 @@
     from miniqdrant.filters.ast import Condition, Filter, HasId, Match, MatchScalar, Range
    +from miniqdrant.filters.cardinality import CardinalityEstimate
     from miniqdrant.filters.evaluate import matches_filter, resolve_path
    +from miniqdrant.filters.index import CandidateSet, PayloadIndexSet, PayloadSchema

     __all__ = [
    +    "CandidateSet",
    +    "CardinalityEstimate",
         "Condition",
         "Filter",
         "HasId",
         "Match",
         "MatchScalar",
    +    "PayloadIndexSet",
    +    "PayloadSchema",
         "Range",
         "matches_filter",
         "resolve_path",
     ]
    -
    ```

    **`src/miniqdrant/query/__init__.py`**

    ```diff
    diff --git a/src/miniqdrant/query/__init__.py b/src/miniqdrant/query/__init__.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..720e1532a9085bf98e74d01d267c337b509e97db
    --- /dev/null
    +++ b/src/miniqdrant/query/__init__.py
    @@ -0,0 +1,4 @@
    +from miniqdrant.query.planner import QueryPlanner, SearchPlan, SegmentFacts, Strategy
    +
    +__all__ = ["QueryPlanner", "SearchPlan", "SegmentFacts", "Strategy"]
    +
    ```


### 验证证据

运行 `uv run pytest -q $(cat journey/stages/06-filter-aware-planning/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：Plan 可以缩小 Candidate，但执行始终保持与参考扫描相同的 Filter 和精确分数语义。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 7 章](https://github.com/system-in-miniature/mini-qdrant/blob/main/docs/zh/tutorial/07-planner.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-qdrant/blob/main/journey/stages/06-filter-aware-planning/stage.patch)
