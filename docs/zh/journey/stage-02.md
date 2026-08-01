# Stage 02 · 距离评分与 Top-k

### 目标

实现距离评分与 Top-k，并能从可执行反例、运行时状态与关键语句解释其边界。

??? note "交付文件"
    - `src/miniqdrant/__init__.py`
    - `src/miniqdrant/metrics.py`
    - `src/miniqdrant/topk.py`
    - `tests/unit/test_metrics.py`
    - `tests/unit/test_topk.py`

### 当前遇到的问题

精确搜索需要统一定义 Cosine、Dot、Euclidean Distance、Tie、Limit 与非有限分量。

### 测试契约

#### 先看会坏在哪里

聚焦测试让距离评分与 Top-k经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

??? note "文件差异：tests/unit/test_metrics.py"
    ```diff
    diff --git a/tests/unit/test_metrics.py b/tests/unit/test_metrics.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..4cb2f67ca89af31407ec5acd4d8af86793d0eec7
    --- /dev/null
    +++ b/tests/unit/test_metrics.py
    @@ -0,0 +1,25 @@
    +from __future__ import annotations
    +
    +import pytest
    +
    +from miniqdrant.config import Distance
    +from miniqdrant.errors import InvalidVectorError
    +from miniqdrant.metrics import score
    +
    +
    +def test_dot_score_is_dot_product() -> None:
    +    assert score(Distance.DOT, (1.0, 2.0), (3.0, 4.0)) == pytest.approx(11.0)
    +
    +
    +def test_cosine_score_uses_normalized_vectors() -> None:
    +    assert score(Distance.COSINE, (0.6, 0.8), (0.6, 0.8)) == pytest.approx(1.0)
    +
    +
    +def test_euclid_score_is_negative_squared_distance() -> None:
    +    assert score(Distance.EUCLID, (1.0, 2.0), (3.0, 4.0)) == pytest.approx(-8.0)
    +
    +
    +def test_metric_rejects_dimension_mismatch() -> None:
    +    with pytest.raises(InvalidVectorError, match="dimension"):
    +        score(Distance.DOT, (1.0,), (1.0, 2.0))
    +
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让距离评分与 Top-k经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert score(Distance.DOT, (1.0, 2.0), (3.0, 4.0)) == pytest.approx(11.0)
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/unit/test_topk.py"
    ```diff
    diff --git a/tests/unit/test_topk.py b/tests/unit/test_topk.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..1eef168f91dc234f5c6fa2e340f1f6e10d04c29f
    --- /dev/null
    +++ b/tests/unit/test_topk.py
    @@ -0,0 +1,51 @@
    +from __future__ import annotations
    +
    +from uuid import UUID
    +
    +import pytest
    +
    +from miniqdrant.topk import TopK
    +
    +
    +def test_topk_keeps_only_best_candidates() -> None:
    +    collector = TopK(2)
    +
    +    collector.offer(1, 0.5)
    +    collector.offer(2, 0.9)
    +    collector.offer(3, 0.7)
    +
    +    assert [(item.point_id, item.score) for item in collector.results()] == [
    +        (2, 0.9),
    +        (3, 0.7),
    +    ]
    +    assert len(collector) == 2
    +
    +
    +def test_topk_breaks_equal_scores_by_canonical_id() -> None:
    +    collector = TopK(2)
    +
    +    collector.offer(2, 1.0)
    +    collector.offer(1, 1.0)
    +    collector.offer(3, 1.0)
    +
    +    assert [candidate.point_id for candidate in collector.results()] == [1, 2]
    +
    +
    +def test_integer_ids_sort_before_uuid_ids_on_equal_score() -> None:
    +    collector = TopK(2)
    +    first_uuid = UUID(int=0)
    +
    +    collector.offer(first_uuid, 1.0)
    +    collector.offer(42, 1.0)
    +
    +    assert [candidate.point_id for candidate in collector.results()] == [42, first_uuid]
    +
    +
    +def test_topk_rejects_invalid_capacity_and_non_finite_score() -> None:
    +    with pytest.raises(ValueError, match="positive"):
    +        TopK(0)
    +
    +    collector = TopK(1)
    +    with pytest.raises(ValueError, match="finite"):
    +        collector.offer(1, float("nan"))
    +
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让距离评分与 Top-k经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert score(Distance.DOT, (1.0, 2.0), (3.0, 4.0)) == pytest.approx(11.0)
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是距离评分与 Top-k。精确搜索需要统一定义 Cosine、Dot、Euclidean Distance、Tie、Limit 与非有限分量。

### 为什么需要这个机制

精确搜索需要统一定义 Cosine、Dot、Euclidean Distance、Tie、Limit 与非有限分量。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

所有 Metric 暴露统一的分数越高越好语义，相同分数下 Top-k 顺序保持稳定。

### 机制板块

#### 距离评分与 Top-k机制

所有 Metric 暴露统一的分数越高越好语义，相同分数下 Top-k 顺序保持稳定。

??? note "文件差异：src/miniqdrant/metrics.py"
    ```diff
    diff --git a/src/miniqdrant/metrics.py b/src/miniqdrant/metrics.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..3c43b36fd15a73aeb78bb0200153975807bd2f0c
    --- /dev/null
    +++ b/src/miniqdrant/metrics.py
    @@ -0,0 +1,18 @@
    +from __future__ import annotations
    +
    +import math
    +
    +from miniqdrant.config import Distance
    +from miniqdrant.errors import InvalidVectorError
    +from miniqdrant.models import Vector
    +
    +
    +def score(distance: Distance, left: Vector, right: Vector) -> float:
    +    if len(left) != len(right):
    +        raise InvalidVectorError("vector dimension mismatch during scoring")
    +    if distance in (Distance.DOT, Distance.COSINE):
    +        return math.fsum(a * b for a, b in zip(left, right, strict=True))
    +    if distance is Distance.EUCLID:
    +        return -math.fsum((a - b) ** 2 for a, b in zip(left, right, strict=True))
    +    raise ValueError(f"unsupported distance: {distance}")
    +
    ```

??? note "文件差异：src/miniqdrant/topk.py"
    ```diff
    diff --git a/src/miniqdrant/topk.py b/src/miniqdrant/topk.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..93c5e09ed815f435e77958c3f2180b156eef0da6
    --- /dev/null
    +++ b/src/miniqdrant/topk.py
    @@ -0,0 +1,62 @@
    +from __future__ import annotations
    +
    +import heapq
    +import math
    +from dataclasses import dataclass
    +from typing import Self
    +
    +from miniqdrant.ids import PointId, point_id_sort_key
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class Candidate:
    +    point_id: PointId
    +    score: float
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class _WorstFirst:
    +    candidate: Candidate
    +
    +    def __lt__(self, other: Self) -> bool:
    +        left = self.candidate
    +        right = other.candidate
    +        if left.score != right.score:
    +            return left.score < right.score
    +        return point_id_sort_key(left.point_id) > point_id_sort_key(right.point_id)
    +
    +
    +class TopK:
    +    def __init__(self, capacity: int) -> None:
    +        if capacity < 1:
    +            raise ValueError("TopK capacity must be positive")
    +        self._capacity = capacity
    +        self._heap: list[_WorstFirst] = []
    +
    +    def __len__(self) -> int:
    +        return len(self._heap)
    +
    +    def offer(self, point_id: PointId, score: float) -> None:
    +        if not math.isfinite(score):
    +            raise ValueError("candidate score must be finite")
    +        entry = _WorstFirst(Candidate(point_id, score))
    +        if len(self._heap) < self._capacity:
    +            heapq.heappush(self._heap, entry)
    +            return
    +        if _is_better(entry.candidate, self._heap[0].candidate):
    +            heapq.heapreplace(self._heap, entry)
    +
    +    def results(self) -> tuple[Candidate, ...]:
    +        return tuple(
    +            sorted(
    +                (entry.candidate for entry in self._heap),
    +                key=lambda item: (-item.score, point_id_sort_key(item.point_id)),
    +            )
    +        )
    +
    +
    +def _is_better(left: Candidate, right: Candidate) -> bool:
    +    if left.score != right.score:
    +        return left.score > right.score
    +    return point_id_sort_key(left.point_id) < point_id_sort_key(right.point_id)
    +
    ```

**是什么，为什么现在需要**

核心机制是距离评分与 Top-k。精确搜索需要统一定义 Cosine、Dot、Euclidean Distance、Tie、Limit 与非有限分量。

**在运行时做什么**

所有 Metric 暴露统一的分数越高越好语义，相同分数下 Top-k 顺序保持稳定。

**关键语句理解**

真正要守住的边界是：所有 Metric 暴露统一的分数越高越好语义，相同分数下 Top-k 顺序保持稳定。

#### 包、Fixture 与工程支撑

保持包导出、测试语料、依赖与运行环境可复现。

??? note "支撑文件差异（1 个文件）"
    **`src/miniqdrant/__init__.py`**

    ```diff
    diff --git a/src/miniqdrant/__init__.py b/src/miniqdrant/__init__.py
    index 32e926045fbc464d15dedcca79e9ff2d9919691c..ba71f390797f515553ff2c37ed4c6358d9763f66 100644
    --- a/src/miniqdrant/__init__.py
    +++ b/src/miniqdrant/__init__.py
    @@ -19,8 +19,10 @@ from miniqdrant.errors import (
         SnapshotError,
     )
     from miniqdrant.models import Point, SearchHit, SearchRequest, SearchResult, StoredPoint
    +from miniqdrant.topk import Candidate, TopK

     __all__ = [
    +    "Candidate",
         "ClosedResourceError",
         "CollectionConfig",
         "CollectionExistsError",
    @@ -42,5 +44,5 @@ __all__ = [
         "SearchResult",
         "SnapshotError",
         "StoredPoint",
    +    "TopK",
     ]
    -
    ```


### 验证证据

运行 `uv run pytest -q $(cat journey/stages/02-distance-topk/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：所有 Metric 暴露统一的分数越高越好语义，相同分数下 Top-k 顺序保持稳定。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 2 章](https://github.com/system-in-miniature/mini-qdrant/blob/main/docs/zh/tutorial/02-points-payload.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-qdrant/blob/main/journey/stages/02-distance-topk/stage.patch)
