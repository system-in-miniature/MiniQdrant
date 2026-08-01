# Stage 08 · Versioned immutable segments

### Goal

Build versioned immutable segments and explain its boundary from an executable counterexample, runtime state, and the critical statement.

??? note "Deliverable files"
    - `src/miniqdrant/collection.py`
    - `src/miniqdrant/segment/__init__.py`
    - `src/miniqdrant/segment/immutable.py`
    - `tests/acceptance/test_cross_segment_search.py`
    - `tests/query/test_hnsw_plans.py`

### The problem at this point

Flushed data needs immutable segment files and versioned references while new writes continue in a mutable owner.

### Test contract

#### See the failure first

The focused tests force versioned immutable segments through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

??? note "File diff: tests/acceptance/test_cross_segment_search.py"
    ```diff
    diff --git a/tests/acceptance/test_cross_segment_search.py b/tests/acceptance/test_cross_segment_search.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..7d4df3e0a3141ae69b6057cb608312cdc7d9fb56
    --- /dev/null
    +++ b/tests/acceptance/test_cross_segment_search.py
    @@ -0,0 +1,55 @@
    +from __future__ import annotations
    +
    +from miniqdrant import Database, Distance, Point, SearchRequest
    +
    +
    +def test_latest_version_wins_even_when_old_scores_higher(tmp_path) -> None:
    +    collection = Database.open(tmp_path).create_collection(
    +        "items",
    +        dimension=2,
    +        distance=Distance.DOT,
    +    )
    +    collection.upsert([Point(1, (10.0, 0.0), {"version": "old"})])
    +    collection.flush(indexed=True)
    +    collection.upsert([Point(1, (0.0, 1.0), {"version": "new"})])
    +
    +    hits = collection.search(SearchRequest((1.0, 0.0), 10, exact=True)).hits
    +
    +    assert len(hits) == 1
    +    assert hits[0].id == 1
    +    assert hits[0].score == 0.0
    +    assert hits[0].payload["version"] == "new"
    +
    +
    +def test_delete_overlay_hides_immutable_hnsw_hit(tmp_path) -> None:
    +    collection = Database.open(tmp_path).create_collection(
    +        "items",
    +        dimension=2,
    +        distance=Distance.DOT,
    +    )
    +    collection.upsert([Point(1, (1.0, 0.0), {})])
    +    collection.flush(indexed=True)
    +
    +    collection.delete([1])
    +
    +    assert collection.retrieve([1]) == ()
    +    assert collection.search(SearchRequest((1.0, 0.0), 10)).hits == ()
    +
    +
    +def test_cross_segment_topk_is_globally_ordered(tmp_path) -> None:
    +    collection = Database.open(tmp_path).create_collection(
    +        "items",
    +        dimension=2,
    +        distance=Distance.DOT,
    +    )
    +    collection.upsert([Point(1, (0.7, 0.0), {})])
    +    collection.flush()
    +    collection.upsert([Point(2, (0.9, 0.0), {})])
    +    collection.flush()
    +    collection.upsert([Point(3, (0.8, 0.0), {})])
    +
    +    result = collection.search(SearchRequest((1.0, 0.0), 2, exact=True))
    +
    +    assert [hit.id for hit in result.hits] == [2, 3]
    +    assert collection.count() == 3
    +
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force versioned immutable segments through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert self._hnsw is not None
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

??? note "File diff: tests/query/test_hnsw_plans.py"
    ```diff
    diff --git a/tests/query/test_hnsw_plans.py b/tests/query/test_hnsw_plans.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..1057999e2a4a2d4016c266a2cf7bbbf8309d1fe2
    --- /dev/null
    +++ b/tests/query/test_hnsw_plans.py
    @@ -0,0 +1,73 @@
    +from __future__ import annotations
    +
    +from miniqdrant.config import CollectionConfig, Distance, HnswConfig, OptimizerConfig
    +from miniqdrant.filters import Filter, Match
    +from miniqdrant.filters.index import PayloadSchema
    +from miniqdrant.models import Point
    +from miniqdrant.segment import ImmutableSegment, MutableSegment, SegmentSearchRequest
    +
    +
    +def indexed_segment() -> ImmutableSegment:
    +    config = CollectionConfig(
    +        dimension=2,
    +        distance=Distance.DOT,
    +        hnsw=HnswConfig(m=4, ef_construct=16, ef_search=8, seed=4),
    +        optimizer=OptimizerConfig(
    +            flush_threshold_points=10,
    +            indexing_threshold_points=1,
    +            target_segment_count=2,
    +        ),
    +    )
    +    mutable = MutableSegment(config)
    +    mutable.create_payload_index("kind", PayloadSchema.KEYWORD)
    +    for point_id in range(1, 21):
    +        mutable.apply_upsert(
    +            Point(
    +                point_id,
    +                (float(point_id), 1.0),
    +                {"kind": "book" if point_id % 2 else "movie"},
    +            ),
    +            version=point_id,
    +        )
    +    return ImmutableSegment.build(
    +        config,
    +        mutable.iter_records(),
    +        payload_schemas=mutable.payload_indexes.schemas,
    +        indexed=True,
    +    )
    +
    +
    +def test_large_indexed_segment_uses_hnsw() -> None:
    +    segment = indexed_segment()
    +
    +    result = segment.search(
    +        SegmentSearchRequest(vector=(1.0, 0.0), limit=3, exact=False)
    +    )
    +
    +    assert result.strategy == "hnsw"
    +    assert [item.point_id for item in result.candidates] == [20, 19, 18]
    +
    +
    +def test_filtered_hnsw_never_returns_residual_mismatch() -> None:
    +    segment = indexed_segment()
    +
    +    result = segment.search(
    +        SegmentSearchRequest(
    +            vector=(1.0, 0.0),
    +            limit=5,
    +            filter=Filter(must=(Match("kind", "book"),)),
    +            exact=False,
    +        )
    +    )
    +
    +    assert result.strategy == "filtered_hnsw"
    +    assert all(segment.get(item.point_id).payload["kind"] == "book" for item in result.candidates)
    +
    +
    +def test_exact_request_bypasses_hnsw() -> None:
    +    result = indexed_segment().search(
    +        SegmentSearchRequest(vector=(1.0, 0.0), limit=3, exact=True)
    +    )
    +
    +    assert result.strategy == "exact_full_scan"
    +
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force versioned immutable segments through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert self._hnsw is not None
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is versioned immutable segments. Flushed data needs immutable segment files and versioned references while new writes continue in a mutable owner.

### Why this mechanism is necessary

Flushed data needs immutable segment files and versioned references while new writes continue in a mutable owner. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

readers observe a stable published segment set and merge results by current point identity rather than stale copies.

### Mechanism blocks

#### Versioned immutable segments mechanism

readers observe a stable published segment set and merge results by current point identity rather than stale copies.

??? note "File diff: src/miniqdrant/collection.py"
    ```diff
    diff --git a/src/miniqdrant/collection.py b/src/miniqdrant/collection.py
    index f4fb5b1bbb6d272db8052cbfb0c52227af8932c2..a87dc9d3e52af15c2a47690245833708a6328847 100644
    --- a/src/miniqdrant/collection.py
    +++ b/src/miniqdrant/collection.py
    @@ -19,7 +19,8 @@ from miniqdrant.models import (
         StoredPoint,
         validate_point,
     )
    -from miniqdrant.segment import MutableSegment, SegmentSearchRequest
    +from miniqdrant.segment import ImmutableSegment, MutableSegment, SegmentSearchRequest
    +from miniqdrant.topk import TopK


     class Collection(Lifecycle):
    @@ -30,6 +31,7 @@ class Collection(Lifecycle):
             self._config = config
             self._update_lock = RLock()
             self._mutable = MutableSegment(config)
    +        self._segments: list[ImmutableSegment] = []
             self._version = 0

         @property
    @@ -47,7 +49,7 @@ class Collection(Lifecycle):
         def count(self) -> int:
             self._ensure_open()
             with self._update_lock:
    -            return self._mutable.live_count
    +            return sum(not point.deleted for point in self._latest_records().values())

         def upsert(self, points: Iterable[Point]) -> int:
             self._ensure_open()
    @@ -76,16 +78,37 @@ class Collection(Lifecycle):
         def create_payload_index(self, path: str, schema: PayloadSchema | str) -> None:
             self._ensure_open()
             with self._update_lock:
    -            self._mutable.create_payload_index(path, PayloadSchema(schema))
    +            normalized = PayloadSchema(schema)
    +            self._mutable.create_payload_index(path, normalized)
    +            for segment in self._segments:
    +                segment.create_payload_index(path, normalized)
    +
    +    def flush(self, *, indexed: bool = False) -> None:
    +        self._ensure_open()
    +        with self._update_lock:
    +            if self._mutable.total_count == 0:
    +                return
    +            schemas = self._mutable.payload_indexes.schemas
    +            segment = ImmutableSegment.build(
    +                self._config,
    +                self._mutable.iter_records(),
    +                payload_schemas=schemas,
    +                indexed=indexed,
    +            )
    +            self._segments.append(segment)
    +            self._mutable = MutableSegment(self._config)
    +            for path, schema in schemas.items():
    +                self._mutable.create_payload_index(path, schema)

         def retrieve(self, point_ids: Iterable[object]) -> tuple[StoredPoint, ...]:
             self._ensure_open()
             identifiers = tuple(canonicalize_point_id(item) for item in point_ids)
             with self._update_lock:
    +            latest = self._latest_records()
                 return tuple(
                     point
                     for point_id in identifiers
    -                if (point := self._mutable.get(point_id)) is not None
    +                if (point := latest.get(point_id)) is not None and not point.deleted
                 )

         def search(self, request: SearchRequest) -> SearchResult:
    @@ -97,32 +120,45 @@ class Collection(Lifecycle):
             if request.score_threshold is not None and not math.isfinite(request.score_threshold):
                 raise ValueError("score threshold must be finite")
             with self._update_lock:
    -            segment_result = self._mutable.search(
    -                SegmentSearchRequest(
    -                    vector=tuple(request.vector),
    -                    limit=request.limit,
    -                    filter=request.filter,
    -                    exact=request.exact,
    -                    ef_search=request.ef_search,
    +            latest = self._latest_records()
    +            search_segments = [*self._segments, self._mutable]
    +            local_limit = request.limit + max(0, len(search_segments) - 1)
    +            segment_results = tuple(
    +                segment.search(
    +                    SegmentSearchRequest(
    +                        vector=tuple(request.vector),
    +                        limit=local_limit,
    +                        filter=request.filter,
    +                        exact=request.exact,
    +                        ef_search=request.ef_search,
    +                    )
                     )
    +                for segment in search_segments
                 )
    +            collector = TopK(request.limit)
    +            for result in segment_results:
    +                for candidate in result.candidates:
    +                    visible = latest.get(candidate.point_id)
    +                    if (
    +                        visible is None
    +                        or visible.deleted
    +                        or visible.version != candidate.version
    +                    ):
    +                        continue
    +                    if (
    +                        request.score_threshold is not None
    +                        and candidate.score < request.score_threshold
    +                    ):
    +                        continue
    +                    collector.offer(candidate.point_id, candidate.score)
                 hits = tuple(
    -                hit
    -                for candidate in segment_result.candidates
    -                if (
    -                    request.score_threshold is None
    -                    or candidate.score >= request.score_threshold
    -                )
    -                if (
    -                    hit := self._project_hit(
    -                        candidate.point_id,
    -                        candidate.score,
    -                        request,
    -                    )
    -                )
    -                is not None
    +                self._project_hit(latest[item.point_id], item.score, request)
    +                for item in collector.results()
    +            )
    +            return SearchResult(
    +                hits,
    +                plan=tuple(result.strategy for result in segment_results),
                 )
    -            return SearchResult(hits, plan=segment_result.strategy)

         def close(self) -> None:
             self._mark_closed()
    @@ -131,15 +167,25 @@ class Collection(Lifecycle):
             self._version += 1
             return self._version

    +    def _latest_records(self) -> dict[PointId, StoredPoint]:
    +        latest: dict[PointId, StoredPoint] = {}
    +        for segment in self._segments:
    +            for record in segment.iter_records():
    +                current = latest.get(record.id)
    +                if current is None or record.version > current.version:
    +                    latest[record.id] = record
    +        for record in self._mutable.iter_records():
    +            current = latest.get(record.id)
    +            if current is None or record.version > current.version:
    +                latest[record.id] = record
    +        return latest
    +
    +    @staticmethod
         def _project_hit(
    -        self,
    -        point_id: PointId,
    +        point: StoredPoint,
             score: float,
             request: SearchRequest,
    -    ) -> SearchHit | None:
    -        point = self._mutable.get(point_id)
    -        if point is None:
    -            return None
    +    ) -> SearchHit:
             return SearchHit(
                 id=point.id,
                 score=score,
    ```

??? note "File diff: src/miniqdrant/segment/immutable.py"
    ```diff
    diff --git a/src/miniqdrant/segment/immutable.py b/src/miniqdrant/segment/immutable.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..963da13058e16a61860621032e6ff85d657dcd5d
    --- /dev/null
    +++ b/src/miniqdrant/segment/immutable.py
    @@ -0,0 +1,155 @@
    +from __future__ import annotations
    +
    +from collections.abc import Iterable, Mapping
    +
    +from miniqdrant.config import CollectionConfig, Distance
    +from miniqdrant.filters import matches_filter
    +from miniqdrant.filters.index import PayloadIndexSet, PayloadSchema
    +from miniqdrant.ids import PointId
    +from miniqdrant.index.hnsw import HnswIndex
    +from miniqdrant.index.plain import PlainVectorIndex
    +from miniqdrant.models import StoredPoint, normalize_cosine, validate_vector
    +from miniqdrant.query.planner import QueryPlanner, SegmentFacts, Strategy
    +from miniqdrant.segment.base import (
    +    SegmentSearchRequest,
    +    SegmentSearchResult,
    +)
    +
    +
    +class ImmutableSegment:
    +    def __init__(
    +        self,
    +        config: CollectionConfig,
    +        records: Iterable[StoredPoint],
    +        *,
    +        payload_schemas: Mapping[str, PayloadSchema] | None = None,
    +        indexed: bool = False,
    +    ) -> None:
    +        self._config = config
    +        self._records = _highest_versions(records)
    +        self._payload_indexes = PayloadIndexSet(
    +            point.id for point in self._records.values() if not point.deleted
    +        )
    +        for path, schema in (payload_schemas or {}).items():
    +            self._payload_indexes.create(path, schema, self.iter_live())
    +        self._hnsw = (
    +            HnswIndex.build(
    +                self.iter_live(),
    +                distance=config.distance,
    +                config=config.hnsw,
    +            )
    +            if indexed and self.live_count
    +            else None
    +        )
    +
    +    @classmethod
    +    def build(
    +        cls,
    +        config: CollectionConfig,
    +        records: Iterable[StoredPoint],
    +        *,
    +        payload_schemas: Mapping[str, PayloadSchema] | None = None,
    +        indexed: bool = False,
    +    ) -> ImmutableSegment:
    +        return cls(
    +            config,
    +            records,
    +            payload_schemas=payload_schemas,
    +            indexed=indexed,
    +        )
    +
    +    @property
    +    def live_count(self) -> int:
    +        return sum(not point.deleted for point in self._records.values())
    +
    +    @property
    +    def total_count(self) -> int:
    +        return len(self._records)
    +
    +    @property
    +    def payload_schemas(self) -> dict[str, PayloadSchema]:
    +        return self._payload_indexes.schemas
    +
    +    def get_record(self, point_id: PointId) -> StoredPoint | None:
    +        return self._records.get(point_id)
    +
    +    def get(self, point_id: PointId) -> StoredPoint | None:
    +        record = self._records.get(point_id)
    +        if record is None or record.deleted:
    +            return None
    +        return record
    +
    +    def iter_records(self) -> tuple[StoredPoint, ...]:
    +        return tuple(self._records.values())
    +
    +    def iter_live(self) -> tuple[StoredPoint, ...]:
    +        return tuple(point for point in self._records.values() if not point.deleted)
    +
    +    def create_payload_index(self, path: str, schema: PayloadSchema) -> None:
    +        self._payload_indexes.create(path, schema, self.iter_live())
    +
    +    def search(self, request: SegmentSearchRequest) -> SegmentSearchResult:
    +        query = validate_vector(request.vector, self._config.dimension)
    +        if self._config.distance is Distance.COSINE:
    +            query = normalize_cosine(query)
    +        candidates = self._payload_indexes.candidates(request.filter)
    +        planner = QueryPlanner(
    +            plain_threshold=self._config.optimizer.indexing_threshold_points,
    +            filter_scan_threshold=self._config.optimizer.indexing_threshold_points,
    +        )
    +        plan = planner.choose(
    +            SegmentFacts(
    +                total_points=self.live_count,
    +                filtered=candidates.estimate if request.filter is not None else None,
    +                has_hnsw=self._hnsw is not None,
    +                exact_requested=request.exact,
    +            )
    +        )
    +        if plan.strategy in (Strategy.EXACT_FULL_SCAN, Strategy.FILTER_THEN_EXACT):
    +            points = (
    +                point for point in self.iter_live() if point.id in candidates.ids
    +            )
    +            result = PlainVectorIndex(self._config.distance, points).search_with_stats(
    +                query,
    +                request.limit,
    +                candidates.residual,
    +            )
    +            return SegmentSearchResult(
    +                result.candidates,
    +                result.visited_count,
    +                plan.strategy.value,
    +            )
    +
    +        assert self._hnsw is not None
    +        local_limit = min(
    +            self.live_count,
    +            max(request.limit, request.limit * 4 if request.filter is not None else 0),
    +        )
    +        graph_result = self._hnsw.search(
    +            query,
    +            limit=local_limit,
    +            ef_search=request.ef_search,
    +            allowed_ids=candidates.ids if request.filter is not None else None,
    +        )
    +        filtered = tuple(
    +            candidate
    +            for candidate in graph_result.candidates
    +            if (
    +                point := self.get(candidate.point_id)
    +            ) is not None
    +            and matches_filter(point.id, point.payload, candidates.residual)
    +        )[: request.limit]
    +        return SegmentSearchResult(
    +            filtered,
    +            graph_result.visited_count,
    +            plan.strategy.value,
    +        )
    +
    +
    +def _highest_versions(records: Iterable[StoredPoint]) -> dict[PointId, StoredPoint]:
    +    highest: dict[PointId, StoredPoint] = {}
    +    for record in records:
    +        current = highest.get(record.id)
    +        if current is None or record.version > current.version:
    +            highest[record.id] = record
    +    return highest
    ```

**What it is and why it appears**

The central mechanism is versioned immutable segments. Flushed data needs immutable segment files and versioned references while new writes continue in a mutable owner.

**Runtime role**

readers observe a stable published segment set and merge results by current point identity rather than stale copies.

**Statement understanding**

The durable boundary is this: readers observe a stable published segment set and merge results by current point identity rather than stale copies.

#### Package, fixture, and project support

Keep exports, test corpora, dependencies, and the runtime environment reproducible.

??? note "Supporting file diffs (1 file)"
    **`src/miniqdrant/segment/__init__.py`**

    ```diff
    diff --git a/src/miniqdrant/segment/__init__.py b/src/miniqdrant/segment/__init__.py
    index 49eebdc819a89772624720484aa7defcc868940f..7f91d9038e36b5e0236f259a1e41792c6b71b0bd 100644
    --- a/src/miniqdrant/segment/__init__.py
    +++ b/src/miniqdrant/segment/__init__.py
    @@ -3,12 +3,13 @@ from miniqdrant.segment.base import (
         SegmentSearchRequest,
         SegmentSearchResult,
     )
    +from miniqdrant.segment.immutable import ImmutableSegment
     from miniqdrant.segment.mutable import MutableSegment

     __all__ = [
    +    "ImmutableSegment",
         "MutableSegment",
         "ScoredCandidate",
         "SegmentSearchRequest",
         "SegmentSearchResult",
     ]
    -
    ```


### Verification evidence

Run `uv run pytest -q $(cat journey/stages/08-immutable-segments/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: readers observe a stable published segment set and merge results by current point identity rather than stale copies.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 4](https://github.com/system-in-miniature/mini-qdrant/blob/main/docs/tutorial/04-segments.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-qdrant/blob/main/journey/stages/08-immutable-segments/stage.patch)
