# Stage 12 · Quantized candidate rescoring

### Goal

Build quantized candidate rescoring and explain its boundary from an executable counterexample, runtime state, and the critical statement.

??? note "Deliverable files"
    - `src/miniqdrant/index/__init__.py`
    - `src/miniqdrant/index/quantization.py`
    - `src/miniqdrant/query/executor.py`
    - `src/miniqdrant/segment/immutable.py`
    - `tests/index/test_quantization.py`
    - `tests/query/test_quantized_rescore.py`

### The problem at this point

Compressed vectors can accelerate candidate generation only if bounded approximation and exact final scoring are kept distinct.

### Test contract

#### See the failure first

The focused tests force quantized candidate rescoring through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

??? note "File diff: tests/index/test_quantization.py"
    ```diff
    diff --git a/tests/index/test_quantization.py b/tests/index/test_quantization.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..1c8beb505989da6bdc5c816afca2274ce34b8e32
    --- /dev/null
    +++ b/tests/index/test_quantization.py
    @@ -0,0 +1,33 @@
    +from __future__ import annotations
    +
    +import pytest
    +
    +from miniqdrant.index.quantization import ScalarQuantizer
    +
    +
    +def test_int8_round_trip_has_bounded_error() -> None:
    +    vectors = (
    +        (-4.0, 2.0, 9.0),
    +        (0.0, 2.0, 3.0),
    +        (7.0, 2.0, -1.0),
    +    )
    +    quantizer = ScalarQuantizer.fit(vectors)
    +
    +    for vector in vectors:
    +        restored = quantizer.decode(quantizer.encode(vector))
    +        error = max(abs(left - right) for left, right in zip(vector, restored, strict=True))
    +        assert error <= quantizer.max_error_bound + 1e-12
    +
    +
    +def test_constant_dimension_uses_zero_code_and_round_trips() -> None:
    +    quantizer = ScalarQuantizer.fit(((1.0, 5.0), (3.0, 5.0)))
    +
    +    assert quantizer.scales[1] == 0.0
    +    assert quantizer.encode((2.0, 5.0))[1] == 0
    +    assert quantizer.decode((0, 0))[1] == pytest.approx(5.0)
    +
    +
    +@pytest.mark.parametrize("value", [(), ((1.0,), (1.0, 2.0))])
    +def test_fit_rejects_empty_or_ragged_vectors(value) -> None:
    +    with pytest.raises(ValueError):
    +        ScalarQuantizer.fit(value)
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force quantized candidate rescoring through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert self._quantized is not None
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

??? note "File diff: tests/query/test_quantized_rescore.py"
    ```diff
    diff --git a/tests/query/test_quantized_rescore.py b/tests/query/test_quantized_rescore.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..d468824d43c4755651d6f1b0393b1c0373e7aaad
    --- /dev/null
    +++ b/tests/query/test_quantized_rescore.py
    @@ -0,0 +1,99 @@
    +from __future__ import annotations
    +
    +import random
    +
    +import pytest
    +
    +from miniqdrant import (
    +    Database,
    +    Distance,
    +    OptimizerConfig,
    +    Point,
    +    ScalarQuantizationConfig,
    +    SearchRequest,
    +)
    +from miniqdrant.metrics import score
    +
    +
    +def test_quantized_candidates_are_rescored_with_original_vectors(tmp_path) -> None:
    +    collection = Database.open(tmp_path).create_collection(
    +        "items",
    +        dimension=2,
    +        distance=Distance.DOT,
    +        optimizer=OptimizerConfig(indexing_threshold_points=1),
    +        quantization=ScalarQuantizationConfig(oversampling=3),
    +    )
    +    collection.upsert(
    +        [
    +            Point(1, (0.91, 0.11), {}),
    +            Point(2, (0.89, 0.13), {}),
    +            Point(3, (0.20, 0.99), {}),
    +            Point(4, (-0.50, 0.40), {}),
    +        ]
    +    )
    +    collection.flush(indexed=True)
    +    query = (1.0, 0.0)
    +
    +    result = collection.search(SearchRequest(query, limit=2))
    +
    +    assert result.plan == ("quantized_hnsw_rescore",)
    +    assert [hit.id for hit in result.hits] == [1, 2]
    +    originals = {point.id: point.vector for point in collection.retrieve([1, 2])}
    +    assert [hit.score for hit in result.hits] == pytest.approx(
    +        [score(Distance.DOT, query, originals[hit.id]) for hit in result.hits]
    +    )
    +
    +
    +def test_exact_request_bypasses_quantized_candidate_scoring(tmp_path) -> None:
    +    collection = Database.open(tmp_path).create_collection(
    +        "items",
    +        dimension=2,
    +        distance=Distance.EUCLID,
    +        optimizer=OptimizerConfig(indexing_threshold_points=1),
    +        quantization=ScalarQuantizationConfig(),
    +    )
    +    collection.upsert(
    +        [Point(index, (float(index), float(index % 3)), {}) for index in range(12)]
    +    )
    +    collection.flush(indexed=True)
    +    query = (4.25, 1.0)
    +
    +    approximate = collection.search(SearchRequest(query, limit=5))
    +    exact = collection.search(SearchRequest(query, limit=5, exact=True))
    +
    +    assert approximate.hits == exact.hits
    +    assert approximate.plan == ("quantized_hnsw_rescore",)
    +    assert exact.plan == ("exact_full_scan",)
    +
    +
    +def test_quantized_oversampling_reaches_required_recall_floor(tmp_path) -> None:
    +    generator = random.Random(17)
    +    collection = Database.open(tmp_path).create_collection(
    +        "items",
    +        dimension=8,
    +        distance=Distance.DOT,
    +        optimizer=OptimizerConfig(indexing_threshold_points=1),
    +        quantization=ScalarQuantizationConfig(oversampling=4),
    +    )
    +    collection.upsert(
    +        [
    +            Point(
    +                point_id,
    +                tuple(generator.uniform(-1.0, 1.0) for _ in range(8)),
    +                {},
    +            )
    +            for point_id in range(200)
    +        ]
    +    )
    +    collection.flush(indexed=True)
    +
    +    recalls = []
    +    for _ in range(10):
    +        query = tuple(generator.uniform(-1.0, 1.0) for _ in range(8))
    +        approximate = collection.search(SearchRequest(query, limit=10))
    +        exact = collection.search(SearchRequest(query, limit=10, exact=True))
    +        approximate_ids = {hit.id for hit in approximate.hits}
    +        exact_ids = {hit.id for hit in exact.hits}
    +        recalls.append(len(approximate_ids & exact_ids) / len(exact_ids))
    +
    +    assert min(recalls) >= 0.95
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force quantized candidate rescoring through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert self._quantized is not None
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is quantized candidate rescoring. Compressed vectors can accelerate candidate generation only if bounded approximation and exact final scoring are kept distinct.

### Why this mechanism is necessary

Compressed vectors can accelerate candidate generation only if bounded approximation and exact final scoring are kept distinct. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

quantization may change candidate cost but returned scores and ordering come from exact vectors after rescoring.

### Mechanism blocks

#### Quantized candidate rescoring mechanism

quantization may change candidate cost but returned scores and ordering come from exact vectors after rescoring.

??? note "File diff: src/miniqdrant/index/quantization.py"
    ```diff
    diff --git a/src/miniqdrant/index/quantization.py b/src/miniqdrant/index/quantization.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..4eac6fafe3eb2b58323941850a9407019a82f756
    --- /dev/null
    +++ b/src/miniqdrant/index/quantization.py
    @@ -0,0 +1,162 @@
    +from __future__ import annotations
    +
    +import math
    +from collections.abc import Callable, Iterable, Sequence
    +from dataclasses import dataclass
    +
    +from miniqdrant.config import Distance
    +from miniqdrant.ids import PointId
    +from miniqdrant.metrics import score
    +from miniqdrant.models import StoredPoint, Vector
    +from miniqdrant.segment.base import ScoredCandidate
    +from miniqdrant.topk import TopK
    +
    +_MIN_CODE = -128
    +_MAX_CODE = 127
    +_LEVELS = _MAX_CODE - _MIN_CODE
    +
    +type QuantizedVector = tuple[int, ...]
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class ScalarQuantizer:
    +    minima: Vector
    +    scales: Vector
    +
    +    @classmethod
    +    def fit(cls, vectors: Iterable[Sequence[float]]) -> ScalarQuantizer:
    +        materialized = tuple(tuple(float(value) for value in vector) for vector in vectors)
    +        if not materialized:
    +            raise ValueError("quantizer requires at least one vector")
    +        dimension = len(materialized[0])
    +        if dimension == 0 or any(len(vector) != dimension for vector in materialized):
    +            raise ValueError("quantizer vectors must have one non-zero dimension")
    +        if any(not math.isfinite(value) for vector in materialized for value in vector):
    +            raise ValueError("quantizer vectors must be finite")
    +        minima = tuple(min(vector[index] for vector in materialized) for index in range(dimension))
    +        maxima = tuple(max(vector[index] for vector in materialized) for index in range(dimension))
    +        scales = tuple(
    +            0.0 if maximum == minimum else (maximum - minimum) / _LEVELS
    +            for minimum, maximum in zip(minima, maxima, strict=True)
    +        )
    +        return cls(minima, scales)
    +
    +    @property
    +    def dimension(self) -> int:
    +        return len(self.minima)
    +
    +    @property
    +    def max_error_bound(self) -> float:
    +        return max(self.scales, default=0.0) / 2.0
    +
    +    def encode(self, vector: Sequence[float]) -> QuantizedVector:
    +        self._validate_dimension(vector)
    +        codes: list[int] = []
    +        for value, minimum, scale in zip(
    +            vector,
    +            self.minima,
    +            self.scales,
    +            strict=True,
    +        ):
    +            number = float(value)
    +            if not math.isfinite(number):
    +                raise ValueError("quantizer vector components must be finite")
    +            if scale == 0.0:
    +                codes.append(0)
    +                continue
    +            code = round((number - minimum) / scale) + _MIN_CODE
    +            codes.append(min(_MAX_CODE, max(_MIN_CODE, code)))
    +        return tuple(codes)
    +
    +    def decode(self, vector: Sequence[int]) -> Vector:
    +        self._validate_dimension(vector)
    +        return tuple(
    +            minimum if scale == 0.0 else minimum + (int(code) - _MIN_CODE) * scale
    +            for code, minimum, scale in zip(
    +                vector,
    +                self.minima,
    +                self.scales,
    +                strict=True,
    +            )
    +        )
    +
    +    def _validate_dimension(self, vector: Sequence[object]) -> None:
    +        if len(vector) != self.dimension:
    +            raise ValueError(
    +                f"quantized vector dimension must be {self.dimension}, "
    +                f"received {len(vector)}"
    +            )
    +
    +
    +class ScalarQuantizedIndex:
    +    """Approximate candidate scoring followed by exact float rescoring."""
    +
    +    def __init__(
    +        self,
    +        distance: Distance,
    +        points: Iterable[StoredPoint],
    +    ) -> None:
    +        self._distance = distance
    +        self._points = {point.id: point for point in points}
    +        if not self._points:
    +            raise ValueError("quantized index requires at least one point")
    +        self._quantizer = ScalarQuantizer.fit(
    +            point.vector for point in self._points.values()
    +        )
    +        self._codes = {
    +            point_id: self._quantizer.encode(point.vector)
    +            for point_id, point in self._points.items()
    +        }
    +
    +    @property
    +    def quantizer(self) -> ScalarQuantizer:
    +        return self._quantizer
    +
    +    def search(
    +        self,
    +        query: Vector,
    +        *,
    +        limit: int,
    +        oversampling: int,
    +        allowed_ids: frozenset[PointId] | None = None,
    +        predicate: Callable[[StoredPoint], bool] | None = None,
    +    ) -> tuple[tuple[ScoredCandidate, ...], int]:
    +        if limit < 1:
    +            raise ValueError("search limit must be positive")
    +        if oversampling < 1:
    +            raise ValueError("quantization oversampling must be positive")
    +        approximate_query = self._quantizer.decode(self._quantizer.encode(query))
    +        capacity = min(len(self._points), limit * oversampling)
    +        approximate = TopK(max(1, capacity))
    +        visited = 0
    +        for point_id, codes in self._codes.items():
    +            if allowed_ids is not None and point_id not in allowed_ids:
    +                continue
    +            point = self._points[point_id]
    +            if predicate is not None and not predicate(point):
    +                continue
    +            visited += 1
    +            approximate.offer(
    +                point_id,
    +                score(
    +                    self._distance,
    +                    approximate_query,
    +                    self._quantizer.decode(codes),
    +                ),
    +            )
    +
    +        rescored = TopK(limit)
    +        for candidate in approximate.results():
    +            point = self._points[candidate.point_id]
    +            rescored.offer(point.id, score(self._distance, query, point.vector))
    +        return (
    +            tuple(
    +                ScoredCandidate(
    +                    candidate.point_id,
    +                    candidate.score,
    +                    self._points[candidate.point_id].version,
    +                )
    +                for candidate in rescored.results()
    +            ),
    +            visited,
    +        )
    ```

??? note "File diff: src/miniqdrant/query/executor.py"
    ```diff
    diff --git a/src/miniqdrant/query/executor.py b/src/miniqdrant/query/executor.py
    index 7a3c9be82219bbaf1a5b591a9bbe99d0dbfe7a22..042c0e9b097e64ac5d333a18c6784937a31ae619 100644
    --- a/src/miniqdrant/query/executor.py
    +++ b/src/miniqdrant/query/executor.py
    @@ -1,6 +1,42 @@
     from __future__ import annotations

    +from miniqdrant.filters import matches_filter
    +from miniqdrant.filters.index import CandidateSet
    +from miniqdrant.index.quantization import ScalarQuantizedIndex
    +from miniqdrant.models import Vector
     from miniqdrant.query.planner import QueryPlanner, SearchPlan, SegmentFacts, Strategy
    +from miniqdrant.segment.base import ScoredCandidate

    -__all__ = ["QueryPlanner", "SearchPlan", "SegmentFacts", "Strategy"]

    +def execute_quantized_rescore(
    +    index: ScalarQuantizedIndex,
    +    query: Vector,
    +    candidates: CandidateSet,
    +    *,
    +    limit: int,
    +    oversampling: int,
    +) -> tuple[tuple[ScoredCandidate, ...], int]:
    +    return index.search(
    +        query,
    +        limit=limit,
    +        oversampling=oversampling,
    +        allowed_ids=candidates.ids,
    +        predicate=(
    +            None
    +            if candidates.residual is None
    +            else lambda point: matches_filter(
    +                point.id,
    +                point.payload,
    +                candidates.residual,
    +            )
    +        ),
    +    )
    +
    +
    +__all__ = [
    +    "QueryPlanner",
    +    "SearchPlan",
    +    "SegmentFacts",
    +    "Strategy",
    +    "execute_quantized_rescore",
    +]
    ```

??? note "File diff: src/miniqdrant/segment/immutable.py"
    ```diff
    diff --git a/src/miniqdrant/segment/immutable.py b/src/miniqdrant/segment/immutable.py
    index 6e31e81560d1b19919a0b9eb8d9d7295c5e40572..0fe88e2050b8ac154704a407f8e6ae455d08a625 100644
    --- a/src/miniqdrant/segment/immutable.py
    +++ b/src/miniqdrant/segment/immutable.py
    @@ -8,7 +8,9 @@ from miniqdrant.filters.index import PayloadIndexSet, PayloadSchema
     from miniqdrant.ids import PointId
     from miniqdrant.index.hnsw import HnswIndex
     from miniqdrant.index.plain import PlainVectorIndex
    +from miniqdrant.index.quantization import ScalarQuantizedIndex
     from miniqdrant.models import StoredPoint, normalize_cosine, validate_vector
    +from miniqdrant.query.executor import execute_quantized_rescore
     from miniqdrant.query.planner import QueryPlanner, SegmentFacts, Strategy
     from miniqdrant.segment.base import (
         ScoredCandidate,
    @@ -42,6 +44,11 @@ class ImmutableSegment:
                 if indexed and self.live_count
                 else None
             )
    +        self._quantized = (
    +            ScalarQuantizedIndex(config.distance, self.iter_live())
    +            if indexed and config.quantization is not None and self.live_count
    +            else None
    +        )

         @classmethod
         def build(
    @@ -121,6 +128,7 @@ class ImmutableSegment:
                     total_points=self.live_count,
                     filtered=candidates.estimate if request.filter is not None else None,
                     has_hnsw=self._hnsw is not None,
    +                has_quantization=self._quantized is not None,
                     exact_requested=request.exact,
                 )
             )
    @@ -139,6 +147,18 @@ class ImmutableSegment:
                     plan.strategy.value,
                 )

    +        if plan.strategy is Strategy.QUANTIZED_HNSW_RESCORE:
    +            assert self._quantized is not None
    +            assert self._config.quantization is not None
    +            result, visited = execute_quantized_rescore(
    +                self._quantized,
    +                query,
    +                candidates,
    +                limit=request.limit,
    +                oversampling=self._config.quantization.oversampling,
    +            )
    +            return SegmentSearchResult(result, visited, plan.strategy.value)
    +
             assert self._hnsw is not None
             local_limit = min(
                 self.live_count,
    ```

**What it is and why it appears**

The central mechanism is quantized candidate rescoring. Compressed vectors can accelerate candidate generation only if bounded approximation and exact final scoring are kept distinct.

**Runtime role**

quantization may change candidate cost but returned scores and ordering come from exact vectors after rescoring.

**Statement understanding**

The durable boundary is this: quantization may change candidate cost but returned scores and ordering come from exact vectors after rescoring.

#### Package, fixture, and project support

Keep exports, test corpora, dependencies, and the runtime environment reproducible.

??? note "Supporting file diffs (1 file)"
    **`src/miniqdrant/index/__init__.py`**

    ```diff
    diff --git a/src/miniqdrant/index/__init__.py b/src/miniqdrant/index/__init__.py
    index f44f9cc27ccd82680b2e38a9b8eede0795bc01da..3785492a706601ed33f5de3712fa1147f4fa417d 100644
    --- a/src/miniqdrant/index/__init__.py
    +++ b/src/miniqdrant/index/__init__.py
    @@ -1,4 +1,12 @@
     from miniqdrant.index.hnsw import HnswGraph, HnswIndex, HnswSearchResult
     from miniqdrant.index.plain import PlainVectorIndex
    +from miniqdrant.index.quantization import ScalarQuantizedIndex, ScalarQuantizer

    -__all__ = ["HnswGraph", "HnswIndex", "HnswSearchResult", "PlainVectorIndex"]
    +__all__ = [
    +    "HnswGraph",
    +    "HnswIndex",
    +    "HnswSearchResult",
    +    "PlainVectorIndex",
    +    "ScalarQuantizedIndex",
    +    "ScalarQuantizer",
    +]
    ```


### Verification evidence

Run `uv run pytest -q $(cat journey/stages/12-quantized-rescore/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: quantization may change candidate cost but returned scores and ordering come from exact vectors after rescoring.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 8](https://github.com/system-in-miniature/mini-qdrant/blob/main/docs/tutorial/08-quantization.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-qdrant/blob/main/journey/stages/12-quantized-rescore/stage.patch)
