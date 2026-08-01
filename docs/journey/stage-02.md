# Stage 02 · Distance scoring and top-k

### Goal

Build distance scoring and top-k and explain its boundary from an executable counterexample, runtime state, and the critical statement.

??? note "Deliverable files"
    - `src/miniqdrant/__init__.py`
    - `src/miniqdrant/metrics.py`
    - `src/miniqdrant/topk.py`
    - `tests/unit/test_metrics.py`
    - `tests/unit/test_topk.py`

### The problem at this point

Exact search needs one deterministic meaning for cosine, dot, euclidean distance, ties, limits, and non-finite components.

### Test contract

#### See the failure first

The focused tests force distance scoring and top-k through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

??? note "File diff: tests/unit/test_metrics.py"
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

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force distance scoring and top-k through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert score(Distance.DOT, (1.0, 2.0), (3.0, 4.0)) == pytest.approx(11.0)
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

??? note "File diff: tests/unit/test_topk.py"
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

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force distance scoring and top-k through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert score(Distance.DOT, (1.0, 2.0), (3.0, 4.0)) == pytest.approx(11.0)
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is distance scoring and top-k. Exact search needs one deterministic meaning for cosine, dot, euclidean distance, ties, limits, and non-finite components.

### Why this mechanism is necessary

Exact search needs one deterministic meaning for cosine, dot, euclidean distance, ties, limits, and non-finite components. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

all metrics expose a common higher-is-better score and top-k ordering is stable under equal scores.

### Mechanism blocks

#### Distance scoring and top-k mechanism

all metrics expose a common higher-is-better score and top-k ordering is stable under equal scores.

??? note "File diff: src/miniqdrant/metrics.py"
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

??? note "File diff: src/miniqdrant/topk.py"
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

**What it is and why it appears**

The central mechanism is distance scoring and top-k. Exact search needs one deterministic meaning for cosine, dot, euclidean distance, ties, limits, and non-finite components.

**Runtime role**

all metrics expose a common higher-is-better score and top-k ordering is stable under equal scores.

**Statement understanding**

The durable boundary is this: all metrics expose a common higher-is-better score and top-k ordering is stable under equal scores.

#### Package, fixture, and project support

Keep exports, test corpora, dependencies, and the runtime environment reproducible.

??? note "Supporting file diffs (1 file)"
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


### Verification evidence

Run `uv run pytest -q $(cat journey/stages/02-distance-topk/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: all metrics expose a common higher-is-better score and top-k ordering is stable under equal scores.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 2](https://github.com/system-in-miniature/mini-qdrant/blob/main/docs/tutorial/02-points-payload.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-qdrant/blob/main/journey/stages/02-distance-topk/stage.patch)
