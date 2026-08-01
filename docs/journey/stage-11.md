# Stage 11 · Online segment optimization

### Goal

Build online segment optimization and explain its boundary from an executable counterexample, runtime state, and the critical statement.

??? note "Deliverable files"
    - `src/miniqdrant/collection.py`
    - `src/miniqdrant/optimizer/__init__.py`
    - `src/miniqdrant/optimizer/failures.py`
    - `src/miniqdrant/optimizer/optimizer.py`
    - `src/miniqdrant/optimizer/policy.py`
    - `src/miniqdrant/segment/immutable.py`
    - `src/miniqdrant/segment/references.py`
    - `tests/concurrency/test_online_optimize.py`
    - `tests/reliability/test_optimizer_publish.py`
    - `tests/storage/test_merge.py`
    - `tests/storage/test_vacuum.py`
    - `tests/unit/test_optimizer_policy.py`

### The problem at this point

Merge, vacuum, and replacement must reclaim obsolete segment state without blocking readers or publishing partial output.

### Test contract

#### See the failure first

The focused tests force online segment optimization through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

??? note "File diff: tests/concurrency/test_online_optimize.py"
    ```diff
    diff --git a/tests/concurrency/test_online_optimize.py b/tests/concurrency/test_online_optimize.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..b91ab12f41ec6580bc587668eb9205b02c9903f6
    --- /dev/null
    +++ b/tests/concurrency/test_online_optimize.py
    @@ -0,0 +1,45 @@
    +from __future__ import annotations
    +
    +from miniqdrant import Database, Distance, Point, SearchRequest
    +from miniqdrant.optimizer.failures import OptimizationGate
    +
    +
    +def test_write_during_build_wins_after_publish(tmp_path) -> None:
    +    collection = Database.open(tmp_path).create_collection(
    +        "items",
    +        dimension=2,
    +        distance=Distance.DOT,
    +    )
    +    collection.upsert([Point(1, (1.0, 0.0), {"version": "old"})])
    +    gate = OptimizationGate()
    +
    +    handle = collection.start_optimize(gate=gate)
    +    gate.wait_until("sources_captured")
    +    collection.upsert([Point(1, (0.0, 1.0), {"version": "new"})])
    +    assert collection.retrieve([1])[0].payload["version"] == "new"
    +    gate.release("finish_build")
    +    handle.result(timeout=5)
    +
    +    point = collection.retrieve([1])[0]
    +    assert point.payload["version"] == "new"
    +    assert collection.search(SearchRequest((1.0, 0.0), 10, exact=True)).hits[0].score == 0.0
    +
    +
    +def test_existing_view_can_finish_after_merge(tmp_path) -> None:
    +    collection = Database.open(tmp_path).create_collection(
    +        "items",
    +        dimension=2,
    +        distance=Distance.DOT,
    +    )
    +    collection.upsert([Point(1, (1.0, 0.0), {})])
    +    collection.flush(indexed=True)
    +    old_view = collection.capture_view()
    +    old_paths = old_view.segment_paths
    +
    +    collection.optimize()
    +
    +    assert old_view.search(SearchRequest((1.0, 0.0), 1)).hits[0].id == 1
    +    assert all(path.exists() for path in old_paths)
    +    old_view.close()
    +    assert all(not path.exists() for path in old_paths)
    +
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force online segment optimization through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert collection.retrieve([1])[0].payload["version"] == "new"
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

??? note "File diff: tests/reliability/test_optimizer_publish.py"
    ```diff
    diff --git a/tests/reliability/test_optimizer_publish.py b/tests/reliability/test_optimizer_publish.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..2d22447f2d63ef9dce059dc2f26ed6fef8e43152
    --- /dev/null
    +++ b/tests/reliability/test_optimizer_publish.py
    @@ -0,0 +1,40 @@
    +from __future__ import annotations
    +
    +import pytest
    +
    +from miniqdrant import Database, Distance, Point
    +
    +
    +class InjectedFailure(RuntimeError):
    +    pass
    +
    +
    +class ArmedFailure:
    +    def __init__(self) -> None:
    +        self.armed = False
    +
    +    def __call__(self, stage: str) -> None:
    +        if self.armed and stage == "before_current_replace":
    +            self.armed = False
    +            raise InjectedFailure(stage)
    +
    +
    +def test_failed_optimizer_publish_keeps_old_segments_searchable(tmp_path) -> None:
    +    failure = ArmedFailure()
    +    collection = Database.open(tmp_path, failure_injector=failure).create_collection(
    +        "items",
    +        dimension=2,
    +        distance=Distance.DOT,
    +    )
    +    collection.upsert([Point(1, (1.0, 0.0), {})])
    +    collection.flush()
    +    old_paths = collection.segment_paths
    +    failure.armed = True
    +
    +    with pytest.raises(InjectedFailure):
    +        collection.optimize()
    +
    +    assert collection.retrieve([1])[0].id == 1
    +    assert collection.segment_paths == old_paths
    +    assert all(path.exists() for path in old_paths)
    +
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force online segment optimization through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert collection.retrieve([1])[0].payload["version"] == "new"
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

??? note "File diff: tests/storage/test_merge.py"
    ```diff
    diff --git a/tests/storage/test_merge.py b/tests/storage/test_merge.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..595fda6727539feb99410b0dacca6addf8a57250
    --- /dev/null
    +++ b/tests/storage/test_merge.py
    @@ -0,0 +1,26 @@
    +from __future__ import annotations
    +
    +from miniqdrant import Database, Distance, Point
    +
    +
    +def test_merge_reduces_segments_and_preserves_latest_versions(tmp_path) -> None:
    +    collection = Database.open(tmp_path).create_collection(
    +        "items",
    +        dimension=2,
    +        distance=Distance.DOT,
    +    )
    +    collection.upsert([Point(1, (1.0, 0.0), {"value": "old"})])
    +    collection.flush()
    +    collection.upsert([Point(1, (0.0, 1.0), {"value": "new"})])
    +    collection.upsert([Point(2, (1.0, 1.0), {})])
    +    collection.flush()
    +
    +    assert collection.segment_statistics().segment_count == 2
    +
    +    collection.merge()
    +
    +    statistics = collection.segment_statistics()
    +    assert statistics.segment_count == 1
    +    assert statistics.live_points == 2
    +    assert collection.retrieve([1])[0].payload["value"] == "new"
    +
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force online segment optimization through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert collection.retrieve([1])[0].payload["version"] == "new"
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

??? note "File diff: tests/storage/test_vacuum.py"
    ```diff
    diff --git a/tests/storage/test_vacuum.py b/tests/storage/test_vacuum.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..14ed7ab2a31049ae6a3738aab42efab5bebae469
    --- /dev/null
    +++ b/tests/storage/test_vacuum.py
    @@ -0,0 +1,30 @@
    +from __future__ import annotations
    +
    +from miniqdrant import Database, Distance, Point
    +
    +
    +def test_vacuum_drops_obsolete_images_and_tombstones(tmp_path) -> None:
    +    collection = Database.open(tmp_path).create_collection(
    +        "items",
    +        dimension=2,
    +        distance=Distance.DOT,
    +    )
    +    collection.upsert(
    +        [
    +            Point(1, (1.0, 0.0), {}),
    +            Point(2, (0.0, 1.0), {}),
    +        ]
    +    )
    +    collection.flush()
    +    collection.delete([1])
    +    collection.flush()
    +
    +    assert collection.segment_statistics().deleted_points == 1
    +
    +    collection.vacuum()
    +
    +    statistics = collection.segment_statistics()
    +    assert statistics.live_points == 1
    +    assert statistics.deleted_points == 0
    +    assert collection.retrieve([1]) == ()
    +
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force online segment optimization through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert collection.retrieve([1])[0].payload["version"] == "new"
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

??? note "File diff: tests/unit/test_optimizer_policy.py"
    ```diff
    diff --git a/tests/unit/test_optimizer_policy.py b/tests/unit/test_optimizer_policy.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..435a5a0960000f208a1304fc5647919f8865e9a4
    --- /dev/null
    +++ b/tests/unit/test_optimizer_policy.py
    @@ -0,0 +1,49 @@
    +from __future__ import annotations
    +
    +from miniqdrant.config import OptimizerConfig
    +from miniqdrant.optimizer.policy import (
    +    OptimizationKind,
    +    SegmentCandidate,
    +    choose_optimization,
    +)
    +
    +
    +def test_vacuum_has_priority_over_merge_and_indexing() -> None:
    +    plan = choose_optimization(
    +        (
    +            SegmentCandidate("large", live_points=100, deleted_points=0, indexed=False),
    +            SegmentCandidate("stale", live_points=7, deleted_points=3, indexed=False),
    +        ),
    +        OptimizerConfig(
    +            indexing_threshold_points=50,
    +            target_segment_count=1,
    +            deleted_ratio_threshold=0.2,
    +        ),
    +    )
    +
    +    assert plan.kind is OptimizationKind.VACUUM
    +    assert plan.segment_ids == ("stale",)
    +
    +
    +def test_merge_selects_the_two_smallest_segments_deterministically() -> None:
    +    plan = choose_optimization(
    +        (
    +            SegmentCandidate("c", live_points=3, deleted_points=0, indexed=True),
    +            SegmentCandidate("b", live_points=1, deleted_points=0, indexed=True),
    +            SegmentCandidate("a", live_points=1, deleted_points=0, indexed=True),
    +        ),
    +        OptimizerConfig(target_segment_count=2),
    +    )
    +
    +    assert plan.kind is OptimizationKind.MERGE
    +    assert plan.segment_ids == ("a", "b")
    +
    +
    +def test_large_plain_segment_is_selected_for_indexing() -> None:
    +    plan = choose_optimization(
    +        (SegmentCandidate("plain", live_points=10, deleted_points=0, indexed=False),),
    +        OptimizerConfig(indexing_threshold_points=10),
    +    )
    +
    +    assert plan.kind is OptimizationKind.INDEX
    +    assert plan.segment_ids == ("plain",)
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force online segment optimization through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert collection.retrieve([1])[0].payload["version"] == "new"
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is online segment optimization. Merge, vacuum, and replacement must reclaim obsolete segment state without blocking readers or publishing partial output.

### Why this mechanism is necessary

Merge, vacuum, and replacement must reclaim obsolete segment state without blocking readers or publishing partial output. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

optimization builds privately, validates its inputs are still current, then atomically swaps references while old readers finish.

### Mechanism blocks

#### Online segment optimization mechanism

optimization builds privately, validates its inputs are still current, then atomically swaps references while old readers finish.

??? note "File diff: src/miniqdrant/collection.py"
    ```diff
    diff --git a/src/miniqdrant/collection.py b/src/miniqdrant/collection.py
    index 1cbdc9b9ccfd8facf8717a05240e9f30387634da..9a8d336c29cec30d9c73e6b9af0169069e6fe14a 100644
    --- a/src/miniqdrant/collection.py
    +++ b/src/miniqdrant/collection.py
    @@ -1,9 +1,12 @@
     from __future__ import annotations

     import math
    +import shutil
     from collections.abc import Callable, Iterable
    +from concurrent.futures import Future
    +from dataclasses import dataclass
     from pathlib import Path
    -from threading import RLock
    +from threading import RLock, Thread
     from uuid import uuid4

     from miniqdrant.config import CollectionConfig, config_fingerprint
    @@ -20,6 +23,8 @@ from miniqdrant.models import (
         StoredPoint,
         validate_point,
     )
    +from miniqdrant.optimizer.failures import OptimizationGate
    +from miniqdrant.optimizer.optimizer import build_replacement
     from miniqdrant.persistence.manifest import Manifest, ManifestStore
     from miniqdrant.persistence.metadata import (
         CollectionMetadata,
    @@ -35,9 +40,62 @@ from miniqdrant.persistence.wal import (
     )
     from miniqdrant.segment import ImmutableSegment, MutableSegment, SegmentSearchRequest
     from miniqdrant.segment.codec import SegmentCodec, SegmentImage
    +from miniqdrant.segment.references import SegmentHandle
     from miniqdrant.topk import TopK


    +@dataclass(frozen=True, slots=True)
    +class SegmentStatistics:
    +    segment_count: int
    +    live_points: int
    +    deleted_points: int
    +
    +
    +class CollectionView:
    +    """A stable search view whose segment files outlive the request."""
    +
    +    def __init__(
    +        self,
    +        config: CollectionConfig,
    +        handles: tuple[SegmentHandle, ...],
    +        mutable: ImmutableSegment | None,
    +        latest: dict[PointId, StoredPoint],
    +    ) -> None:
    +        self._config = config
    +        self._handles = handles
    +        self._mutable = mutable
    +        self._latest = latest
    +        self._closed = False
    +
    +    @property
    +    def segment_paths(self) -> tuple[Path, ...]:
    +        return tuple(handle.path for handle in self._handles)
    +
    +    def search(self, request: SearchRequest) -> SearchResult:
    +        if self._closed:
    +            raise RuntimeError("collection view is closed")
    +        return _search(
    +            self._config,
    +            tuple(handle.segment for handle in self._handles)
    +            + (() if self._mutable is None else (self._mutable,)),
    +            self._latest,
    +            request,
    +        )
    +
    +    def close(self) -> None:
    +        if self._closed:
    +            return
    +        self._closed = True
    +        for handle in self._handles:
    +            handle.release()
    +
    +    def __enter__(self) -> CollectionView:
    +        return self
    +
    +    def __exit__(self, *_error: object) -> None:
    +        self.close()
    +
    +
     class Collection(Lifecycle):
         def __init__(
             self,
    @@ -48,7 +106,7 @@ class Collection(Lifecycle):
             wal: Wal,
             manifest_store: ManifestStore,
             manifest: Manifest,
    -        segments: list[ImmutableSegment],
    +        segments: list[SegmentHandle],
             payload_schemas: dict[str, PayloadSchema],
             failure_injector: Callable[[str], None] | None = None,
         ) -> None:
    @@ -63,6 +121,7 @@ class Collection(Lifecycle):
             self._payload_schemas = payload_schemas
             self._failure_injector = failure_injector or (lambda _stage: None)
             self._update_lock = RLock()
    +        self._optimizer_lock = RLock()
             self._mutable = self._new_mutable()

         @classmethod
    @@ -114,12 +173,15 @@ class Collection(Lifecycle):
             manifest = store.load_current()
             if manifest.schema_fingerprint != config_fingerprint(metadata.config):
                 raise CorruptionError("manifest schema fingerprint does not match collection")
    -        segments: list[ImmutableSegment] = []
    +        segments: list[SegmentHandle] = []
             for segment_id in manifest.segment_ids:
    -            image = SegmentCodec.read(path / "segments" / segment_id)
    +            segment_path = path / "segments" / segment_id
    +            image = SegmentCodec.read(segment_path)
                 if image.config != metadata.config:
                     raise CorruptionError(f"segment schema mismatch: {segment_id}")
    -            segments.append(image.to_segment())
    +            segments.append(
    +                SegmentHandle(segment_id, segment_path, image.to_segment())
    +            )
             wal = Wal.open(path / "wal", durability)
             collection = cls(
                 metadata.name,
    @@ -154,6 +216,11 @@ class Collection(Lifecycle):
                 path: schema.value for path, schema in sorted(self._payload_schemas.items())
             }

    +    @property
    +    def segment_paths(self) -> tuple[Path, ...]:
    +        with self._update_lock:
    +            return tuple(handle.path for handle in self._segments)
    +
         def count(self) -> int:
             self._ensure_open()
             with self._update_lock:
    @@ -194,8 +261,8 @@ class Collection(Lifecycle):
                 )
                 self._payload_schemas = schemas
                 self._mutable.create_payload_index(path, normalized)
    -            for segment in self._segments:
    -                segment.create_payload_index(path, normalized)
    +            for handle in self._segments:
    +                handle.segment.create_payload_index(path, normalized)

         def flush(self, *, indexed: bool = False) -> None:
             self._ensure_open()
    @@ -210,7 +277,7 @@ class Collection(Lifecycle):
                     payload_schemas=self._payload_schemas,
                     indexed=indexed,
                 )
    -            SegmentCodec.write_atomic(self._path / "segments", image)
    +            segment_path = SegmentCodec.write_atomic(self._path / "segments", image)
                 manifest = Manifest(
                     generation=self._manifest.generation + 1,
                     schema_fingerprint=self._manifest.schema_fingerprint,
    @@ -218,7 +285,9 @@ class Collection(Lifecycle):
                     replay_boundary=self._wal.last_sequence,
                 )
                 self._manifest_store.publish(manifest)
    -            self._segments.append(image.to_segment())
    +            self._segments.append(
    +                SegmentHandle(segment_id, segment_path, image.to_segment())
    +            )
                 self._manifest = manifest
                 self._mutable = self._new_mutable()

    @@ -235,52 +304,74 @@ class Collection(Lifecycle):

         def search(self, request: SearchRequest) -> SearchResult:
             self._ensure_open()
    -        if request.limit < 1:
    -            raise ValueError("search limit must be positive")
    -        if request.filter is not None and not isinstance(request.filter, Filter):
    -            raise InvalidFilterError("search filter must be a Filter")
    -        if request.score_threshold is not None and not math.isfinite(request.score_threshold):
    -            raise ValueError("score threshold must be finite")
    +        with self.capture_view() as view:
    +            return view.search(request)
    +
    +    def capture_view(self) -> CollectionView:
    +        self._ensure_open()
             with self._update_lock:
    -            latest = self._latest_records()
    -            search_segments = [*self._segments, self._mutable]
    -            local_limit = request.limit + max(0, len(search_segments) - 1)
    -            segment_results = tuple(
    -                segment.search(
    -                    SegmentSearchRequest(
    -                        vector=tuple(request.vector),
    -                        limit=local_limit,
    -                        filter=request.filter,
    -                        exact=request.exact,
    -                        ef_search=request.ef_search,
    -                    )
    +            handles = tuple(handle.acquire() for handle in self._segments)
    +            mutable_records = self._mutable.iter_records()
    +            mutable = (
    +                ImmutableSegment.build(
    +                    self._config,
    +                    mutable_records,
    +                    payload_schemas=self._payload_schemas,
                     )
    -                for segment in search_segments
    +                if mutable_records
    +                else None
                 )
    -            collector = TopK(request.limit)
    -            for result in segment_results:
    -                for candidate in result.candidates:
    -                    visible = latest.get(candidate.point_id)
    -                    if (
    -                        visible is None
    -                        or visible.deleted
    -                        or visible.version != candidate.version
    -                    ):
    -                        continue
    -                    if (
    -                        request.score_threshold is not None
    -                        and candidate.score < request.score_threshold
    -                    ):
    -                        continue
    -                    collector.offer(candidate.point_id, candidate.score)
    -            hits = tuple(
    -                self._project_hit(latest[item.point_id], item.score, request)
    -                for item in collector.results()
    +            latest = _latest_records(
    +                tuple(handle.segment for handle in handles),
    +                mutable_records,
                 )
    -            return SearchResult(
    -                hits,
    -                plan=tuple(result.strategy for result in segment_results),
    +            return CollectionView(self._config, handles, mutable, latest)
    +
    +    def segment_statistics(self) -> SegmentStatistics:
    +        self._ensure_open()
    +        with self._update_lock:
    +            records = tuple(
    +                record
    +                for handle in self._segments
    +                for record in handle.segment.iter_records()
                 )
    +            return SegmentStatistics(
    +                segment_count=len(self._segments),
    +                live_points=sum(not record.deleted for record in records),
    +                deleted_points=sum(record.deleted for record in records),
    +            )
    +
    +    def optimize(self, *, gate: OptimizationGate | None = None) -> None:
    +        self._ensure_open()
    +        with self._optimizer_lock:
    +            self._optimize(gate)
    +
    +    def start_optimize(
    +        self,
    +        *,
    +        gate: OptimizationGate | None = None,
    +    ) -> Future[None]:
    +        self._ensure_open()
    +        result: Future[None] = Future()
    +
    +        def run() -> None:
    +            if not result.set_running_or_notify_cancel():
    +                return
    +            try:
    +                self.optimize(gate=gate)
    +            except BaseException as error:
    +                result.set_exception(error)
    +            else:
    +                result.set_result(None)
    +
    +        Thread(target=run, name=f"optimize-{self._name}", daemon=True).start()
    +        return result
    +
    +    def merge(self) -> None:
    +        self.optimize()
    +
    +    def vacuum(self) -> None:
    +        self.optimize()

         def close(self) -> None:
             if not self._mark_closed():
    @@ -310,17 +401,99 @@ class Collection(Lifecycle):
                     self._mutable.apply_delete(point_id, record.sequence)

         def _latest_records(self) -> dict[PointId, StoredPoint]:
    -        latest: dict[PointId, StoredPoint] = {}
    -        for segment in self._segments:
    -            for record in segment.iter_records():
    -                current = latest.get(record.id)
    -                if current is None or record.version > current.version:
    -                    latest[record.id] = record
    -        for record in self._mutable.iter_records():
    -            current = latest.get(record.id)
    -            if current is None or record.version > current.version:
    -                latest[record.id] = record
    -        return latest
    +        return _latest_records(
    +            tuple(handle.segment for handle in self._segments),
    +            self._mutable.iter_records(),
    +        )
    +
    +    def _optimize(self, gate: OptimizationGate | None) -> None:
    +        with self._update_lock:
    +            sources = tuple(handle.acquire() for handle in self._segments)
    +            captured_records = tuple(
    +                record
    +                for handle in sources
    +                for record in handle.segment.iter_records()
    +            ) + self._mutable.iter_records()
    +            replay_boundary = self._wal.last_sequence
    +
    +        segment_id = f"seg-{uuid4().hex}"
    +        segment_path = self._path / "segments" / segment_id
    +        manifest: Manifest | None = None
    +        published = False
    +        try:
    +            if gate is not None:
    +                gate.arrive("sources_captured")
    +                gate.wait_for_release("finish_build")
    +            image = build_replacement(
    +                segment_id=segment_id,
    +                config=self._config,
    +                records=captured_records,
    +                payload_schemas=self._payload_schemas,
    +                drop_tombstones=True,
    +            )
    +            SegmentCodec.write_atomic(self._path / "segments", image)
    +            with self._update_lock:
    +                source_ids = {handle.segment_id for handle in sources}
    +                preserved = [
    +                    handle
    +                    for handle in self._segments
    +                    if handle.segment_id not in source_ids
    +                ]
    +                manifest = Manifest(
    +                    generation=self._manifest.generation + 1,
    +                    schema_fingerprint=self._manifest.schema_fingerprint,
    +                    segment_ids=(
    +                        *(handle.segment_id for handle in preserved),
    +                        segment_id,
    +                    ),
    +                    replay_boundary=replay_boundary,
    +                )
    +                late_records = tuple(
    +                    record
    +                    for record in self._mutable.iter_records()
    +                    if record.version > replay_boundary
    +                )
    +                replacement = SegmentHandle(
    +                    segment_id,
    +                    segment_path,
    +                    image.to_segment(),
    +                )
    +                next_mutable = self._mutable_from_records(late_records)
    +                self._manifest_store.publish(manifest)
    +                published = True
    +                self._segments = [
    +                    *preserved,
    +                    replacement,
    +                ]
    +                self._manifest = manifest
    +                self._mutable = next_mutable
    +                for handle in sources:
    +                    handle.retire()
    +        except BaseException:
    +            if manifest is not None and not published:
    +                (self._path / manifest.filename).unlink(missing_ok=True)
    +                (self._path / "CURRENT.tmp").unlink(missing_ok=True)
    +            if segment_path.exists() and not published:
    +                shutil.rmtree(segment_path)
    +            raise
    +        finally:
    +            for handle in sources:
    +                handle.release()
    +
    +    def _mutable_from_records(
    +        self,
    +        records: Iterable[StoredPoint],
    +    ) -> MutableSegment:
    +        mutable = self._new_mutable()
    +        for record in records:
    +            if record.deleted:
    +                mutable.apply_delete(record.id, record.version)
    +            else:
    +                mutable.apply_upsert(
    +                    Point(record.id, record.vector, record.payload),
    +                    record.version,
    +                )
    +        return mutable

         @staticmethod
         def _project_hit(
    @@ -334,3 +507,71 @@ class Collection(Lifecycle):
                 payload=point.payload if request.with_payload else None,
                 vector=point.vector if request.with_vector else None,
             )
    +
    +
    +def _latest_records(
    +    segments: Iterable[ImmutableSegment],
    +    extra_records: Iterable[StoredPoint],
    +) -> dict[PointId, StoredPoint]:
    +    latest: dict[PointId, StoredPoint] = {}
    +    for segment in segments:
    +        for record in segment.iter_records():
    +            current = latest.get(record.id)
    +            if current is None or record.version > current.version:
    +                latest[record.id] = record
    +    for record in extra_records:
    +        current = latest.get(record.id)
    +        if current is None or record.version > current.version:
    +            latest[record.id] = record
    +    return latest
    +
    +
    +def _search(
    +    config: CollectionConfig,
    +    segments: tuple[ImmutableSegment, ...],
    +    latest: dict[PointId, StoredPoint],
    +    request: SearchRequest,
    +) -> SearchResult:
    +    if request.limit < 1:
    +        raise ValueError("search limit must be positive")
    +    if request.filter is not None and not isinstance(request.filter, Filter):
    +        raise InvalidFilterError("search filter must be a Filter")
    +    if request.score_threshold is not None and not math.isfinite(request.score_threshold):
    +        raise ValueError("score threshold must be finite")
    +    local_limit = request.limit + max(0, len(segments) - 1)
    +    segment_results = tuple(
    +        segment.search(
    +            SegmentSearchRequest(
    +                vector=tuple(request.vector),
    +                limit=local_limit,
    +                filter=request.filter,
    +                exact=request.exact,
    +                ef_search=request.ef_search,
    +            )
    +        )
    +        for segment in segments
    +    )
    +    collector = TopK(request.limit)
    +    for result in segment_results:
    +        for candidate in result.candidates:
    +            visible = latest.get(candidate.point_id)
    +            if (
    +                visible is None
    +                or visible.deleted
    +                or visible.version != candidate.version
    +            ):
    +                continue
    +            if (
    +                request.score_threshold is not None
    +                and candidate.score < request.score_threshold
    +            ):
    +                continue
    +            collector.offer(candidate.point_id, candidate.score)
    +    hits = tuple(
    +        Collection._project_hit(latest[item.point_id], item.score, request)
    +        for item in collector.results()
    +    )
    +    return SearchResult(
    +        hits,
    +        plan=tuple(result.strategy for result in segment_results),
    +    )
    ```

??? note "File diff: src/miniqdrant/optimizer/failures.py"
    ```diff
    diff --git a/src/miniqdrant/optimizer/failures.py b/src/miniqdrant/optimizer/failures.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..118ef19888b2507d24a8019883fcc50b57da4392
    --- /dev/null
    +++ b/src/miniqdrant/optimizer/failures.py
    @@ -0,0 +1,29 @@
    +from __future__ import annotations
    +
    +from threading import Event, Lock
    +
    +
    +class OptimizationGate:
    +    """Deterministic synchronization points for optimizer fault tests."""
    +
    +    def __init__(self) -> None:
    +        self._lock = Lock()
    +        self._events: dict[str, Event] = {}
    +
    +    def arrive(self, stage: str) -> None:
    +        self._event(stage).set()
    +
    +    def wait_until(self, stage: str, timeout: float = 5.0) -> None:
    +        if not self._event(stage).wait(timeout):
    +            raise TimeoutError(f"optimizer did not reach stage: {stage}")
    +
    +    def release(self, stage: str) -> None:
    +        self._event(stage).set()
    +
    +    def wait_for_release(self, stage: str, timeout: float = 5.0) -> None:
    +        if not self._event(stage).wait(timeout):
    +            raise TimeoutError(f"optimizer was not released at stage: {stage}")
    +
    +    def _event(self, stage: str) -> Event:
    +        with self._lock:
    +            return self._events.setdefault(stage, Event())
    ```

??? note "File diff: src/miniqdrant/optimizer/optimizer.py"
    ```diff
    diff --git a/src/miniqdrant/optimizer/optimizer.py b/src/miniqdrant/optimizer/optimizer.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..739330c1c5f7515aae33f7099c3154370a9d9dc4
    --- /dev/null
    +++ b/src/miniqdrant/optimizer/optimizer.py
    @@ -0,0 +1,40 @@
    +from __future__ import annotations
    +
    +from collections.abc import Iterable, Mapping
    +
    +from miniqdrant.config import CollectionConfig
    +from miniqdrant.filters.index import PayloadSchema
    +from miniqdrant.ids import PointId
    +from miniqdrant.models import StoredPoint
    +from miniqdrant.segment.codec import SegmentImage
    +
    +
    +def select_latest(records: Iterable[StoredPoint]) -> dict[PointId, StoredPoint]:
    +    latest: dict[PointId, StoredPoint] = {}
    +    for record in records:
    +        current = latest.get(record.id)
    +        if current is None or record.version > current.version:
    +            latest[record.id] = record
    +    return latest
    +
    +
    +def build_replacement(
    +    *,
    +    segment_id: str,
    +    config: CollectionConfig,
    +    records: Iterable[StoredPoint],
    +    payload_schemas: Mapping[str, PayloadSchema],
    +    drop_tombstones: bool,
    +) -> SegmentImage:
    +    latest = select_latest(records)
    +    return SegmentImage.build(
    +        segment_id=segment_id,
    +        config=config,
    +        records=(
    +            record
    +            for record in latest.values()
    +            if not drop_tombstones or not record.deleted
    +        ),
    +        payload_schemas=payload_schemas,
    +        indexed=True,
    +    )
    ```

??? note "File diff: src/miniqdrant/optimizer/policy.py"
    ```diff
    diff --git a/src/miniqdrant/optimizer/policy.py b/src/miniqdrant/optimizer/policy.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..20897327ba36b8abcbdb763d0d31e28c437a6543
    --- /dev/null
    +++ b/src/miniqdrant/optimizer/policy.py
    @@ -0,0 +1,73 @@
    +from __future__ import annotations
    +
    +from dataclasses import dataclass
    +from enum import StrEnum
    +
    +from miniqdrant.config import OptimizerConfig
    +
    +
    +class OptimizationKind(StrEnum):
    +    VACUUM = "vacuum"
    +    MERGE = "merge"
    +    INDEX = "index"
    +    NONE = "none"
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class SegmentCandidate:
    +    segment_id: str
    +    live_points: int
    +    deleted_points: int
    +    indexed: bool
    +
    +    @property
    +    def total_points(self) -> int:
    +        return self.live_points + self.deleted_points
    +
    +    @property
    +    def deleted_ratio(self) -> float:
    +        if self.total_points == 0:
    +            return 0.0
    +        return self.deleted_points / self.total_points
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class OptimizationPlan:
    +    kind: OptimizationKind
    +    segment_ids: tuple[str, ...]
    +
    +
    +def choose_optimization(
    +    candidates: tuple[SegmentCandidate, ...],
    +    config: OptimizerConfig,
    +) -> OptimizationPlan:
    +    stale = tuple(
    +        candidate
    +        for candidate in candidates
    +        if candidate.deleted_ratio >= config.deleted_ratio_threshold
    +    )
    +    if stale:
    +        selected = min(stale, key=lambda item: (-item.deleted_ratio, item.segment_id))
    +        return OptimizationPlan(OptimizationKind.VACUUM, (selected.segment_id,))
    +
    +    if len(candidates) > config.target_segment_count:
    +        smallest = sorted(
    +            candidates,
    +            key=lambda item: (item.total_points, item.segment_id),
    +        )[:2]
    +        return OptimizationPlan(
    +            OptimizationKind.MERGE,
    +            tuple(candidate.segment_id for candidate in smallest),
    +        )
    +
    +    plain = tuple(
    +        candidate
    +        for candidate in candidates
    +        if not candidate.indexed
    +        and candidate.live_points >= config.indexing_threshold_points
    +    )
    +    if plain:
    +        selected = min(plain, key=lambda item: (-item.live_points, item.segment_id))
    +        return OptimizationPlan(OptimizationKind.INDEX, (selected.segment_id,))
    +
    +    return OptimizationPlan(OptimizationKind.NONE, ())
    ```

??? note "File diff: src/miniqdrant/segment/immutable.py"
    ```diff
    diff --git a/src/miniqdrant/segment/immutable.py b/src/miniqdrant/segment/immutable.py
    index 06bd26e2bc6844e9d1f3d0700f15c3503d835658..6e31e81560d1b19919a0b9eb8d9d7295c5e40572 100644
    --- a/src/miniqdrant/segment/immutable.py
    +++ b/src/miniqdrant/segment/immutable.py
    @@ -67,6 +67,14 @@ class ImmutableSegment:
         def total_count(self) -> int:
             return len(self._records)

    +    @property
    +    def deleted_count(self) -> int:
    +        return self.total_count - self.live_count
    +
    +    @property
    +    def indexed(self) -> bool:
    +        return self._hnsw is not None
    +
         @property
         def payload_schemas(self) -> dict[str, PayloadSchema]:
             return self._payload_indexes.schemas
    ```

??? note "File diff: src/miniqdrant/segment/references.py"
    ```diff
    diff --git a/src/miniqdrant/segment/references.py b/src/miniqdrant/segment/references.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..ba083a188ff16ccf41c0e1a7a87db047c7a65d69
    --- /dev/null
    +++ b/src/miniqdrant/segment/references.py
    @@ -0,0 +1,49 @@
    +from __future__ import annotations
    +
    +import shutil
    +from pathlib import Path
    +from threading import Lock
    +
    +from miniqdrant.segment.immutable import ImmutableSegment
    +
    +
    +class SegmentHandle:
    +    """Reference-counted ownership for a published immutable segment."""
    +
    +    def __init__(
    +        self,
    +        segment_id: str,
    +        path: Path,
    +        segment: ImmutableSegment,
    +    ) -> None:
    +        self.segment_id = segment_id
    +        self.path = path
    +        self.segment = segment
    +        self._lock = Lock()
    +        self._references = 0
    +        self._retired = False
    +
    +    def acquire(self) -> SegmentHandle:
    +        with self._lock:
    +            if self._retired and self._references == 0:
    +                raise RuntimeError("cannot acquire a deleted segment")
    +            self._references += 1
    +        return self
    +
    +    def release(self) -> None:
    +        delete = False
    +        with self._lock:
    +            if self._references == 0:
    +                raise RuntimeError("segment handle released without an acquisition")
    +            self._references -= 1
    +            delete = self._retired and self._references == 0
    +        if delete:
    +            shutil.rmtree(self.path, ignore_errors=True)
    +
    +    def retire(self) -> None:
    +        delete = False
    +        with self._lock:
    +            self._retired = True
    +            delete = self._references == 0
    +        if delete:
    +            shutil.rmtree(self.path, ignore_errors=True)
    ```

**What it is and why it appears**

The central mechanism is online segment optimization. Merge, vacuum, and replacement must reclaim obsolete segment state without blocking readers or publishing partial output.

**Runtime role**

optimization builds privately, validates its inputs are still current, then atomically swaps references while old readers finish.

**Statement understanding**

The durable boundary is this: optimization builds privately, validates its inputs are still current, then atomically swaps references while old readers finish.

#### Package, fixture, and project support

Keep exports, test corpora, dependencies, and the runtime environment reproducible.

??? note "Supporting file diffs (1 file)"
    **`src/miniqdrant/optimizer/__init__.py`**

    ```diff
    diff --git a/src/miniqdrant/optimizer/__init__.py b/src/miniqdrant/optimizer/__init__.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..50cb72b29db3ad2a6bef96e20030d16c901e5d38
    --- /dev/null
    +++ b/src/miniqdrant/optimizer/__init__.py
    @@ -0,0 +1,15 @@
    +from miniqdrant.optimizer.failures import OptimizationGate
    +from miniqdrant.optimizer.policy import (
    +    OptimizationKind,
    +    OptimizationPlan,
    +    SegmentCandidate,
    +    choose_optimization,
    +)
    +
    +__all__ = [
    +    "OptimizationGate",
    +    "OptimizationKind",
    +    "OptimizationPlan",
    +    "SegmentCandidate",
    +    "choose_optimization",
    +]
    ```


### Verification evidence

Run `uv run pytest -q $(cat journey/stages/11-online-optimization/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: optimization builds privately, validates its inputs are still current, then atomically swaps references while old readers finish.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 9](https://github.com/system-in-miniature/mini-qdrant/blob/main/docs/tutorial/09-optimizer.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-qdrant/blob/main/journey/stages/11-online-optimization/stage.patch)
