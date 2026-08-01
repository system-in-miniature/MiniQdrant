# Stage 10 · Manifest publication and recovery

### Goal

Build manifest publication and recovery and explain its boundary from an executable counterexample, runtime state, and the critical statement.

??? note "Deliverable files"
    - `src/miniqdrant/__init__.py`
    - `src/miniqdrant/collection.py`
    - `src/miniqdrant/config.py`
    - `src/miniqdrant/database.py`
    - `src/miniqdrant/persistence/__init__.py`
    - `src/miniqdrant/persistence/manifest.py`
    - `src/miniqdrant/persistence/metadata.py`
    - `src/miniqdrant/segment/codec.py`
    - `src/miniqdrant/segment/immutable.py`
    - `tests/acceptance/test_cross_restart.py`
    - `tests/reliability/test_crash_boundaries.py`
    - `tests/reliability/test_manifest_publish.py`
    - `tests/reliability/test_restart.py`
    - `tests/storage/test_manifest.py`
    - `tests/storage/test_segment_codec.py`

### The problem at this point

Segment files, collection metadata, manifest generations, and wal replay need one restart protocol with an atomic publication point.

### Test contract

#### See the failure first

The focused tests force manifest publication and recovery through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

??? note "File diff: tests/acceptance/test_cross_restart.py"
    ```diff
    diff --git a/tests/acceptance/test_cross_restart.py b/tests/acceptance/test_cross_restart.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..6af87cd07b8a53b040c52e54e124ac44c9703964
    --- /dev/null
    +++ b/tests/acceptance/test_cross_restart.py
    @@ -0,0 +1,33 @@
    +from __future__ import annotations
    +
    +from miniqdrant import Database, Distance, Filter, Match, Point, SearchRequest
    +
    +
    +def test_cross_restart_preserves_version_delete_filter_and_order(tmp_path) -> None:
    +    database = Database.open(tmp_path)
    +    collection = database.create_collection("items", dimension=2, distance=Distance.DOT)
    +    collection.create_payload_index("kind", "keyword")
    +    collection.upsert(
    +        [
    +            Point(1, (1.0, 0.0), {"kind": "book"}),
    +            Point(2, (0.9, 0.1), {"kind": "book"}),
    +        ]
    +    )
    +    collection.flush(indexed=True)
    +    collection.delete([1])
    +    collection.upsert([Point(2, (0.8, 0.2), {"kind": "book", "version": "new"})])
    +    database.close()
    +
    +    reopened = Database.open(tmp_path).collection("items")
    +    result = reopened.search(
    +        SearchRequest(
    +            (1.0, 0.0),
    +            10,
    +            filter=Filter(must=(Match("kind", "book"),)),
    +            exact=True,
    +        )
    +    )
    +
    +    assert [hit.id for hit in result.hits] == [2]
    +    assert result.hits[0].payload["version"] == "new"
    +
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force manifest publication and recovery through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert [hit.id for hit in result.hits] == [2]
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

??? note "File diff: tests/reliability/test_crash_boundaries.py"
    ```diff
    diff --git a/tests/reliability/test_crash_boundaries.py b/tests/reliability/test_crash_boundaries.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..e915d569038ac6d9d2b83a071b7ffd742d876d29
    --- /dev/null
    +++ b/tests/reliability/test_crash_boundaries.py
    @@ -0,0 +1,52 @@
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
    +class OneShotFailure:
    +    def __init__(self, stage: str) -> None:
    +        self.stage = stage
    +        self.armed = True
    +
    +    def __call__(self, stage: str) -> None:
    +        if self.armed and stage == self.stage:
    +            self.armed = False
    +            raise InjectedFailure(stage)
    +
    +
    +def test_crash_after_wal_fsync_before_apply_recovers_once(tmp_path) -> None:
    +    failure = OneShotFailure("after_wal_fsync")
    +    database = Database.open(tmp_path, failure_injector=failure)
    +    collection = database.create_collection("items", dimension=2, distance=Distance.DOT)
    +
    +    with pytest.raises(InjectedFailure):
    +        collection.upsert([Point(1, (1.0, 0.0), {})])
    +
    +    database.simulate_process_loss()
    +    reopened = Database.open(tmp_path).collection("items")
    +
    +    assert reopened.count() == 1
    +    assert reopened.retrieve([1])[0].version == 1
    +
    +
    +def test_failed_manifest_publish_replays_wal_without_half_segment(tmp_path) -> None:
    +    failure = OneShotFailure("before_current_replace")
    +    database = Database.open(tmp_path, failure_injector=failure)
    +    collection = database.create_collection("items", dimension=2, distance=Distance.DOT)
    +    collection.upsert([Point(1, (1.0, 0.0), {})])
    +
    +    with pytest.raises(InjectedFailure):
    +        collection.flush(indexed=True)
    +
    +    database.simulate_process_loss()
    +    reopened = Database.open(tmp_path).collection("items")
    +
    +    assert reopened.count() == 1
    +    assert reopened.retrieve([1])[0].version == 1
    +
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force manifest publication and recovery through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert [hit.id for hit in result.hits] == [2]
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

??? note "File diff: tests/reliability/test_manifest_publish.py"
    ```diff
    diff --git a/tests/reliability/test_manifest_publish.py b/tests/reliability/test_manifest_publish.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..a8cbbf3a634599f375d219d7722e776d02554669
    --- /dev/null
    +++ b/tests/reliability/test_manifest_publish.py
    @@ -0,0 +1,27 @@
    +from __future__ import annotations
    +
    +import pytest
    +
    +from miniqdrant.persistence.manifest import Manifest, ManifestStore
    +
    +
    +class InjectedFailure(RuntimeError):
    +    pass
    +
    +
    +def test_failed_current_swap_keeps_old_manifest(tmp_path) -> None:
    +    armed = False
    +
    +    def fail(stage: str) -> None:
    +        if armed and stage == "before_current_replace":
    +            raise InjectedFailure(stage)
    +
    +    store = ManifestStore(tmp_path, failure_injector=fail)
    +    store.publish(Manifest(1, "schema", ("seg-a",), 10))
    +    armed = True
    +
    +    with pytest.raises(InjectedFailure):
    +        store.publish(Manifest(2, "schema", ("seg-b",), 20))
    +
    +    assert store.load_current() == Manifest(1, "schema", ("seg-a",), 10)
    +
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force manifest publication and recovery through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert [hit.id for hit in result.hits] == [2]
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

??? note "File diff: tests/reliability/test_restart.py"
    ```diff
    diff --git a/tests/reliability/test_restart.py b/tests/reliability/test_restart.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..4009790d5fd54f57b67e8050d7606e7501e4f891
    --- /dev/null
    +++ b/tests/reliability/test_restart.py
    @@ -0,0 +1,42 @@
    +from __future__ import annotations
    +
    +from miniqdrant import Database, Distance, Point, SearchRequest
    +from miniqdrant.persistence import Durability
    +
    +
    +def test_acknowledged_unflushed_upsert_survives_restart(tmp_path) -> None:
    +    database = Database.open(tmp_path, durability=Durability.ALWAYS)
    +    collection = database.create_collection("items", dimension=2, distance=Distance.DOT)
    +    collection.upsert([Point(1, (1.0, 0.0), {"state": "wal-only"})])
    +
    +    database.simulate_process_loss()
    +    reopened = Database.open(tmp_path, durability=Durability.ALWAYS)
    +
    +    assert reopened.collection("items").retrieve([1])[0].payload["state"] == "wal-only"
    +
    +
    +def test_flushed_segments_and_later_wal_suffix_restore_together(tmp_path) -> None:
    +    database = Database.open(tmp_path)
    +    collection = database.create_collection("items", dimension=2, distance=Distance.DOT)
    +    collection.upsert([Point(1, (1.0, 0.0), {"state": "segment"})])
    +    collection.flush(indexed=True)
    +    collection.upsert([Point(2, (0.0, 1.0), {"state": "wal"})])
    +    database.simulate_process_loss()
    +
    +    reopened = Database.open(tmp_path).collection("items")
    +
    +    assert [point.id for point in reopened.retrieve([1, 2])] == [1, 2]
    +    assert reopened.search(SearchRequest((1.0, 0.0), 2, exact=True)).hits[0].id == 1
    +
    +
    +def test_payload_index_schema_survives_restart(tmp_path) -> None:
    +    database = Database.open(tmp_path)
    +    collection = database.create_collection("items", dimension=2, distance=Distance.DOT)
    +    collection.create_payload_index("kind", "keyword")
    +    collection.upsert([Point(1, (1.0, 0.0), {"kind": "book"})])
    +    database.close()
    +
    +    reopened = Database.open(tmp_path).collection("items")
    +
    +    assert reopened.payload_index_schemas == {"kind": "keyword"}
    +
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force manifest publication and recovery through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert [hit.id for hit in result.hits] == [2]
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

??? note "File diff: tests/storage/test_manifest.py"
    ```diff
    diff --git a/tests/storage/test_manifest.py b/tests/storage/test_manifest.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..2ae30dc6747fce800813ce2fb704ef241cd42cb6
    --- /dev/null
    +++ b/tests/storage/test_manifest.py
    @@ -0,0 +1,42 @@
    +from __future__ import annotations
    +
    +import pytest
    +
    +from miniqdrant.errors import CorruptionError
    +from miniqdrant.persistence.manifest import Manifest, ManifestStore
    +
    +
    +def manifest(generation: int, *segments: str) -> Manifest:
    +    return Manifest(
    +        generation=generation,
    +        schema_fingerprint="schema-1",
    +        segment_ids=segments,
    +        replay_boundary=generation * 10,
    +    )
    +
    +
    +def test_manifest_publish_and_load_current(tmp_path) -> None:
    +    store = ManifestStore(tmp_path)
    +
    +    store.publish(manifest(1, "seg-a"))
    +    store.publish(manifest(2, "seg-a", "seg-b"))
    +
    +    assert store.load_current() == manifest(2, "seg-a", "seg-b")
    +    assert (tmp_path / "CURRENT").read_text() == "manifest-00000000000000000002.json\n"
    +
    +
    +def test_manifest_generation_must_increase(tmp_path) -> None:
    +    store = ManifestStore(tmp_path)
    +    store.publish(manifest(2, "seg-a"))
    +
    +    with pytest.raises(ValueError, match="generation"):
    +        store.publish(manifest(2, "seg-b"))
    +
    +
    +def test_missing_current_manifest_is_corruption(tmp_path) -> None:
    +    store = ManifestStore(tmp_path)
    +    (tmp_path / "CURRENT").write_text("manifest-00000000000000000099.json\n")
    +
    +    with pytest.raises(CorruptionError, match="manifest"):
    +        store.load_current()
    +
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force manifest publication and recovery through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert [hit.id for hit in result.hits] == [2]
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

??? note "File diff: tests/storage/test_segment_codec.py"
    ```diff
    diff --git a/tests/storage/test_segment_codec.py b/tests/storage/test_segment_codec.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..1f75c5555e6a3c189c547c28549a30a183b67984
    --- /dev/null
    +++ b/tests/storage/test_segment_codec.py
    @@ -0,0 +1,73 @@
    +from __future__ import annotations
    +
    +import os
    +
    +import pytest
    +
    +from miniqdrant.config import CollectionConfig, Distance, HnswConfig
    +from miniqdrant.errors import CorruptionError
    +from miniqdrant.filters.index import PayloadSchema
    +from miniqdrant.models import Point
    +from miniqdrant.segment import MutableSegment
    +from miniqdrant.segment.codec import SegmentCodec, SegmentImage
    +
    +
    +def image() -> SegmentImage:
    +    config = CollectionConfig(
    +        dimension=2,
    +        distance=Distance.COSINE,
    +        hnsw=HnswConfig(m=4, ef_construct=16, ef_search=8, seed=9),
    +    )
    +    mutable = MutableSegment(config)
    +    mutable.create_payload_index("kind", PayloadSchema.KEYWORD)
    +    mutable.apply_upsert(Point(1, (1.0, 0.0), {"kind": "book"}), version=1)
    +    mutable.apply_upsert(Point(2, (0.0, 1.0), {"kind": "movie"}), version=2)
    +    mutable.apply_delete(3, version=3)
    +    return SegmentImage.build(
    +        segment_id="seg-test",
    +        config=config,
    +        records=mutable.iter_records(),
    +        payload_schemas=mutable.payload_indexes.schemas,
    +        indexed=True,
    +    )
    +
    +
    +def test_segment_round_trip_preserves_semantics(tmp_path) -> None:
    +    original = image()
    +
    +    path = SegmentCodec.write_atomic(tmp_path / "segments", original)
    +    restored = SegmentCodec.read(path)
    +
    +    assert restored.semantic_fingerprint() == original.semantic_fingerprint()
    +    assert restored.to_segment().search_exact((1.0, 0.0), limit=1)[0].point_id == 1
    +    assert {
    +        "meta.json",
    +        "points.bin",
    +        "payloads.bin",
    +        "versions.bin",
    +        "deleted.bin",
    +        "hnsw.bin",
    +        "payload-indexes.bin",
    +    } <= {item.name for item in path.iterdir()}
    +
    +
    +def test_segment_checksum_corruption_is_fatal(tmp_path) -> None:
    +    path = SegmentCodec.write_atomic(tmp_path / "segments", image())
    +    points = path / "points.bin"
    +    with points.open("r+b") as stream:
    +        stream.seek(-1, os.SEEK_END)
    +        value = stream.read(1)
    +        stream.seek(-1, os.SEEK_END)
    +        stream.write(bytes([value[0] ^ 0xFF]))
    +
    +    with pytest.raises(CorruptionError, match="checksum"):
    +        SegmentCodec.read(path)
    +
    +
    +def test_existing_segment_is_never_overwritten(tmp_path) -> None:
    +    root = tmp_path / "segments"
    +    SegmentCodec.write_atomic(root, image())
    +
    +    with pytest.raises(FileExistsError):
    +        SegmentCodec.write_atomic(root, image())
    +
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force manifest publication and recovery through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert [hit.id for hit in result.hits] == [2]
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is manifest publication and recovery. Segment files, collection metadata, manifest generations, and wal replay need one restart protocol with an atomic publication point.

### Why this mechanism is necessary

Segment files, collection metadata, manifest generations, and wal replay need one restart protocol with an atomic publication point. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

restart opens one complete manifest generation then replays only the ordered WAL suffix not already represented by it.

### Mechanism blocks

#### Manifest publication and recovery mechanism

restart opens one complete manifest generation then replays only the ordered WAL suffix not already represented by it.

??? note "File diff: src/miniqdrant/collection.py"
    ```diff
    diff --git a/src/miniqdrant/collection.py b/src/miniqdrant/collection.py
    index a87dc9d3e52af15c2a47690245833708a6328847..1cbdc9b9ccfd8facf8717a05240e9f30387634da 100644
    --- a/src/miniqdrant/collection.py
    +++ b/src/miniqdrant/collection.py
    @@ -1,12 +1,13 @@
     from __future__ import annotations

     import math
    -from collections.abc import Iterable
    +from collections.abc import Callable, Iterable
     from pathlib import Path
     from threading import RLock
    +from uuid import uuid4

    -from miniqdrant.config import CollectionConfig
    -from miniqdrant.errors import InvalidFilterError
    +from miniqdrant.config import CollectionConfig, config_fingerprint
    +from miniqdrant.errors import CorruptionError, InvalidFilterError
     from miniqdrant.filters import Filter
     from miniqdrant.filters.index import PayloadSchema
     from miniqdrant.ids import PointId, canonicalize_point_id
    @@ -19,20 +20,121 @@ from miniqdrant.models import (
         StoredPoint,
         validate_point,
     )
    +from miniqdrant.persistence.manifest import Manifest, ManifestStore
    +from miniqdrant.persistence.metadata import (
    +    CollectionMetadata,
    +    read_collection_metadata,
    +    write_collection_metadata,
    +)
    +from miniqdrant.persistence.wal import (
    +    DeleteOperation,
    +    Durability,
    +    UpsertOperation,
    +    Wal,
    +    WalRecord,
    +)
     from miniqdrant.segment import ImmutableSegment, MutableSegment, SegmentSearchRequest
    +from miniqdrant.segment.codec import SegmentCodec, SegmentImage
     from miniqdrant.topk import TopK


     class Collection(Lifecycle):
    -    def __init__(self, name: str, path: Path, config: CollectionConfig) -> None:
    +    def __init__(
    +        self,
    +        name: str,
    +        path: Path,
    +        config: CollectionConfig,
    +        *,
    +        wal: Wal,
    +        manifest_store: ManifestStore,
    +        manifest: Manifest,
    +        segments: list[ImmutableSegment],
    +        payload_schemas: dict[str, PayloadSchema],
    +        failure_injector: Callable[[str], None] | None = None,
    +    ) -> None:
             super().__init__()
             self._name = name
             self._path = path
             self._config = config
    +        self._wal = wal
    +        self._manifest_store = manifest_store
    +        self._manifest = manifest
    +        self._segments = segments
    +        self._payload_schemas = payload_schemas
    +        self._failure_injector = failure_injector or (lambda _stage: None)
             self._update_lock = RLock()
    -        self._mutable = MutableSegment(config)
    -        self._segments: list[ImmutableSegment] = []
    -        self._version = 0
    +        self._mutable = self._new_mutable()
    +
    +    @classmethod
    +    def create(
    +        cls,
    +        name: str,
    +        path: Path,
    +        config: CollectionConfig,
    +        *,
    +        durability: Durability,
    +        failure_injector: Callable[[str], None] | None = None,
    +    ) -> Collection:
    +        path.mkdir(parents=True, exist_ok=False)
    +        (path / "segments").mkdir()
    +        metadata = CollectionMetadata(name, config, {})
    +        write_collection_metadata(path / "collection.json", metadata)
    +        wal = Wal.create(path / "wal", durability)
    +        initial_store = ManifestStore(path)
    +        manifest = Manifest(
    +            generation=1,
    +            schema_fingerprint=config_fingerprint(config),
    +            segment_ids=(),
    +            replay_boundary=0,
    +        )
    +        initial_store.publish(manifest)
    +        store = ManifestStore(path, failure_injector=failure_injector)
    +        return cls(
    +            name,
    +            path,
    +            config,
    +            wal=wal,
    +            manifest_store=store,
    +            manifest=manifest,
    +            segments=[],
    +            payload_schemas={},
    +            failure_injector=failure_injector,
    +        )
    +
    +    @classmethod
    +    def open(
    +        cls,
    +        path: Path,
    +        *,
    +        durability: Durability,
    +        failure_injector: Callable[[str], None] | None = None,
    +    ) -> Collection:
    +        metadata = read_collection_metadata(path / "collection.json")
    +        store = ManifestStore(path, failure_injector=failure_injector)
    +        manifest = store.load_current()
    +        if manifest.schema_fingerprint != config_fingerprint(metadata.config):
    +            raise CorruptionError("manifest schema fingerprint does not match collection")
    +        segments: list[ImmutableSegment] = []
    +        for segment_id in manifest.segment_ids:
    +            image = SegmentCodec.read(path / "segments" / segment_id)
    +            if image.config != metadata.config:
    +                raise CorruptionError(f"segment schema mismatch: {segment_id}")
    +            segments.append(image.to_segment())
    +        wal = Wal.open(path / "wal", durability)
    +        collection = cls(
    +            metadata.name,
    +            path,
    +            metadata.config,
    +            wal=wal,
    +            manifest_store=store,
    +            manifest=manifest,
    +            segments=segments,
    +            payload_schemas=metadata.payload_schemas,
    +            failure_injector=failure_injector,
    +        )
    +        for record in wal.replay(after_sequence=manifest.replay_boundary):
    +            collection._apply_wal_record(record)
    +        return collection

         @property
         def name(self) -> str:
    @@ -46,6 +148,12 @@ class Collection(Lifecycle):
         def config(self) -> CollectionConfig:
             return self._config

    +    @property
    +    def payload_index_schemas(self) -> dict[str, str]:
    +        return {
    +            path: schema.value for path, schema in sorted(self._payload_schemas.items())
    +        }
    +
         def count(self) -> int:
             self._ensure_open()
             with self._update_lock:
    @@ -59,10 +167,10 @@ class Collection(Lifecycle):
             for point in batch:
                 validate_point(point, self._config)
             with self._update_lock:
    -            version = self._next_version()
    -            for point in batch:
    -                self._mutable.apply_upsert(point, version)
    -            return version
    +            record = self._wal.append(UpsertOperation(batch))
    +            self._failure_injector("after_wal_fsync")
    +            self._apply_wal_record(record)
    +            return record.sequence

         def delete(self, point_ids: Iterable[object]) -> int:
             self._ensure_open()
    @@ -70,15 +178,21 @@ class Collection(Lifecycle):
             if not identifiers:
                 raise ValueError("delete batch must not be empty")
             with self._update_lock:
    -            version = self._next_version()
    -            for point_id in identifiers:
    -                self._mutable.apply_delete(point_id, version)
    -            return version
    +            record = self._wal.append(DeleteOperation(identifiers))
    +            self._failure_injector("after_wal_fsync")
    +            self._apply_wal_record(record)
    +            return record.sequence

         def create_payload_index(self, path: str, schema: PayloadSchema | str) -> None:
             self._ensure_open()
    +        normalized = PayloadSchema(schema)
             with self._update_lock:
    -            normalized = PayloadSchema(schema)
    +            schemas = {**self._payload_schemas, path: normalized}
    +            write_collection_metadata(
    +                self._path / "collection.json",
    +                CollectionMetadata(self._name, self._config, schemas),
    +            )
    +            self._payload_schemas = schemas
                 self._mutable.create_payload_index(path, normalized)
                 for segment in self._segments:
                     segment.create_payload_index(path, normalized)
    @@ -88,17 +202,25 @@ class Collection(Lifecycle):
             with self._update_lock:
                 if self._mutable.total_count == 0:
                     return
    -            schemas = self._mutable.payload_indexes.schemas
    -            segment = ImmutableSegment.build(
    -                self._config,
    -                self._mutable.iter_records(),
    -                payload_schemas=schemas,
    +            segment_id = f"seg-{uuid4().hex}"
    +            image = SegmentImage.build(
    +                segment_id=segment_id,
    +                config=self._config,
    +                records=self._mutable.iter_records(),
    +                payload_schemas=self._payload_schemas,
                     indexed=indexed,
                 )
    -            self._segments.append(segment)
    -            self._mutable = MutableSegment(self._config)
    -            for path, schema in schemas.items():
    -                self._mutable.create_payload_index(path, schema)
    +            SegmentCodec.write_atomic(self._path / "segments", image)
    +            manifest = Manifest(
    +                generation=self._manifest.generation + 1,
    +                schema_fingerprint=self._manifest.schema_fingerprint,
    +                segment_ids=(*self._manifest.segment_ids, segment_id),
    +                replay_boundary=self._wal.last_sequence,
    +            )
    +            self._manifest_store.publish(manifest)
    +            self._segments.append(image.to_segment())
    +            self._manifest = manifest
    +            self._mutable = self._new_mutable()

         def retrieve(self, point_ids: Iterable[object]) -> tuple[StoredPoint, ...]:
             self._ensure_open()
    @@ -161,11 +283,31 @@ class Collection(Lifecycle):
                 )

         def close(self) -> None:
    -        self._mark_closed()
    +        if not self._mark_closed():
    +            return
    +        self._wal.flush()
    +        self._wal.close()
    +
    +    def simulate_process_loss(self) -> None:
    +        if not self._mark_closed():
    +            return
    +        self._wal.close()
    +
    +    def _new_mutable(self) -> MutableSegment:
    +        mutable = MutableSegment(self._config)
    +        for path, schema in self._payload_schemas.items():
    +            mutable.create_payload_index(path, schema)
    +        return mutable

    -    def _next_version(self) -> int:
    -        self._version += 1
    -        return self._version
    +    def _apply_wal_record(self, record: WalRecord) -> None:
    +        if isinstance(record.operation, UpsertOperation):
    +            for point in record.operation.points:
    +                validate_point(point, self._config)
    +            for point in record.operation.points:
    +                self._mutable.apply_upsert(point, record.sequence)
    +        else:
    +            for point_id in record.operation.point_ids:
    +                self._mutable.apply_delete(point_id, record.sequence)

         def _latest_records(self) -> dict[PointId, StoredPoint]:
             latest: dict[PointId, StoredPoint] = {}
    ```

??? note "File diff: src/miniqdrant/config.py"
    ```diff
    diff --git a/src/miniqdrant/config.py b/src/miniqdrant/config.py
    index 8308e82cfaa10e0ae0aa33e26f15d248bb80887f..93688d6398d8241fea12eebf15c4022af4efce2f 100644
    --- a/src/miniqdrant/config.py
    +++ b/src/miniqdrant/config.py
    @@ -1,6 +1,8 @@
     from __future__ import annotations

    -from dataclasses import dataclass, field
    +import hashlib
    +import json
    +from dataclasses import asdict, dataclass, field
     from enum import StrEnum


    @@ -66,3 +68,41 @@ class CollectionConfig:
                 raise ValueError("collection dimension must be positive")
             if not isinstance(self.distance, Distance):
                 object.__setattr__(self, "distance", Distance(self.distance))
    +
    +
    +def config_to_dict(config: CollectionConfig) -> dict[str, object]:
    +    return {
    +        "dimension": config.dimension,
    +        "distance": config.distance.value,
    +        "hnsw": asdict(config.hnsw),
    +        "optimizer": asdict(config.optimizer),
    +        "quantization": (
    +            None if config.quantization is None else asdict(config.quantization)
    +        ),
    +    }
    +
    +
    +def config_from_dict(value: object) -> CollectionConfig:
    +    if not isinstance(value, dict):
    +        raise ValueError("collection config must be an object")
    +    quantization = value["quantization"]
    +    return CollectionConfig(
    +        dimension=int(value["dimension"]),
    +        distance=Distance(value["distance"]),
    +        hnsw=HnswConfig(**value["hnsw"]),
    +        optimizer=OptimizerConfig(**value["optimizer"]),
    +        quantization=(
    +            None
    +            if quantization is None
    +            else ScalarQuantizationConfig(**quantization)
    +        ),
    +    )
    +
    +
    +def config_fingerprint(config: CollectionConfig) -> str:
    +    encoded = json.dumps(
    +        config_to_dict(config),
    +        sort_keys=True,
    +        separators=(",", ":"),
    +    ).encode()
    +    return hashlib.sha256(encoded).hexdigest()
    ```

??? note "File diff: src/miniqdrant/database.py"
    ```diff
    diff --git a/src/miniqdrant/database.py b/src/miniqdrant/database.py
    index 112ce44dadbd8022b5bf8cec1e72663709d2ef75..2b831bce3e83ef2659739c37f3dfec3f71a0dd3b 100644
    --- a/src/miniqdrant/database.py
    +++ b/src/miniqdrant/database.py
    @@ -1,6 +1,8 @@
     from __future__ import annotations

     import re
    +import shutil
    +from collections.abc import Callable
     from pathlib import Path
     from threading import RLock

    @@ -17,22 +19,49 @@ from miniqdrant.errors import (
         CollectionNotFoundError,
     )
     from miniqdrant.lifecycle import Lifecycle
    +from miniqdrant.persistence.wal import Durability

     _COLLECTION_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


     class Database(Lifecycle):
    -    def __init__(self, path: Path) -> None:
    +    def __init__(
    +        self,
    +        path: Path,
    +        *,
    +        durability: Durability,
    +        failure_injector: Callable[[str], None] | None,
    +    ) -> None:
             super().__init__()
             self._path = path
    +        self._durability = Durability(durability)
    +        self._failure_injector = failure_injector
             self._collections_path = path / "collections"
             self._collections_path.mkdir(parents=True, exist_ok=True)
             self._lock = RLock()
             self._collections: dict[str, Collection] = {}
    +        for collection_path in sorted(self._collections_path.iterdir()):
    +            if collection_path.is_dir() and (collection_path / "collection.json").is_file():
    +                collection = Collection.open(
    +                    collection_path,
    +                    durability=self._durability,
    +                    failure_injector=failure_injector,
    +                )
    +                self._collections[collection.name] = collection

         @classmethod
    -    def open(cls, path: str | Path) -> Database:
    -        return cls(Path(path))
    +    def open(
    +        cls,
    +        path: str | Path,
    +        *,
    +        durability: Durability = Durability.ALWAYS,
    +        failure_injector: Callable[[str], None] | None = None,
    +    ) -> Database:
    +        return cls(
    +            Path(path),
    +            durability=durability,
    +            failure_injector=failure_injector,
    +        )

         @property
         def path(self) -> Path:
    @@ -61,8 +90,15 @@ class Database(Lifecycle):
                 if name in self._collections:
                     raise CollectionExistsError(f"collection already exists: {name}")
                 path = self._collections_path / name
    -            path.mkdir(parents=True, exist_ok=False)
    -            collection = Collection(name, path, config)
    +            if path.exists():
    +                raise CollectionExistsError(f"collection directory already exists: {name}")
    +            collection = Collection.create(
    +                name,
    +                path,
    +                config,
    +                durability=self._durability,
    +                failure_injector=self._failure_injector,
    +            )
                 self._collections[name] = collection
                 return collection

    @@ -82,6 +118,7 @@ class Database(Lifecycle):
                 except KeyError as error:
                     raise CollectionNotFoundError(f"collection not found: {name}") from error
                 collection.close()
    +            shutil.rmtree(collection.path)

         def close(self) -> None:
             if not self._mark_closed():
    @@ -92,6 +129,15 @@ class Database(Lifecycle):
             for collection in collections:
                 collection.close()

    +    def simulate_process_loss(self) -> None:
    +        if not self._mark_closed():
    +            return
    +        with self._lock:
    +            collections = tuple(self._collections.values())
    +            self._collections.clear()
    +        for collection in collections:
    +            collection.simulate_process_loss()
    +

     def _validate_collection_name(name: str) -> None:
         if not _COLLECTION_NAME.fullmatch(name):
    ```

??? note "File diff: src/miniqdrant/persistence/manifest.py"
    ```diff
    diff --git a/src/miniqdrant/persistence/manifest.py b/src/miniqdrant/persistence/manifest.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..45b10857fe07bd363e14595914f8ae51db894caa
    --- /dev/null
    +++ b/src/miniqdrant/persistence/manifest.py
    @@ -0,0 +1,130 @@
    +from __future__ import annotations
    +
    +import hashlib
    +import json
    +import os
    +from collections.abc import Callable
    +from dataclasses import asdict, dataclass
    +from pathlib import Path
    +
    +from miniqdrant.errors import CorruptionError
    +from miniqdrant.persistence.fsync import fsync_directory
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class Manifest:
    +    generation: int
    +    schema_fingerprint: str
    +    segment_ids: tuple[str, ...]
    +    replay_boundary: int
    +
    +    def __post_init__(self) -> None:
    +        if self.generation < 1:
    +            raise ValueError("manifest generation must be positive")
    +        if self.replay_boundary < 0:
    +            raise ValueError("manifest replay boundary must be non-negative")
    +        object.__setattr__(self, "segment_ids", tuple(self.segment_ids))
    +
    +    @property
    +    def filename(self) -> str:
    +        return f"manifest-{self.generation:020d}.json"
    +
    +
    +class ManifestStore:
    +    def __init__(
    +        self,
    +        path: str | Path,
    +        *,
    +        failure_injector: Callable[[str], None] | None = None,
    +    ) -> None:
    +        self._path = Path(path)
    +        self._path.mkdir(parents=True, exist_ok=True)
    +        self._failure_injector = failure_injector or (lambda _stage: None)
    +
    +    def publish(self, manifest: Manifest) -> None:
    +        current = self._load_current_optional()
    +        if current is not None and manifest.generation <= current.generation:
    +            raise ValueError("manifest generation must increase")
    +        target = self._path / manifest.filename
    +        payload = _encode_manifest(manifest)
    +        temporary = target.with_suffix(".json.tmp")
    +        _write_fsynced(temporary, payload)
    +        os.replace(temporary, target)
    +        fsync_directory(self._path)
    +
    +        current_temporary = self._path / "CURRENT.tmp"
    +        _write_fsynced(current_temporary, f"{manifest.filename}\n".encode())
    +        self._failure_injector("before_current_replace")
    +        os.replace(current_temporary, self._path / "CURRENT")
    +        fsync_directory(self._path)
    +
    +    def load_current(self) -> Manifest:
    +        current = self._load_current_optional()
    +        if current is None:
    +            raise CorruptionError("CURRENT manifest pointer is missing")
    +        return current
    +
    +    def _load_current_optional(self) -> Manifest | None:
    +        current_path = self._path / "CURRENT"
    +        if not current_path.exists():
    +            return None
    +        try:
    +            filename = current_path.read_text().strip()
    +            if Path(filename).name != filename or not filename.startswith("manifest-"):
    +                raise CorruptionError("invalid CURRENT manifest pointer")
    +            path = self._path / filename
    +            return _decode_manifest(path.read_bytes())
    +        except CorruptionError:
    +            raise
    +        except (OSError, UnicodeDecodeError) as error:
    +            raise CorruptionError("current manifest cannot be loaded") from error
    +
    +
    +def _encode_manifest(manifest: Manifest) -> bytes:
    +    payload = asdict(manifest)
    +    payload["segment_ids"] = list(manifest.segment_ids)
    +    canonical = _canonical_json(payload)
    +    envelope = {
    +        "format_version": 1,
    +        "payload": payload,
    +        "sha256": hashlib.sha256(canonical).hexdigest(),
    +    }
    +    return _canonical_json(envelope)
    +
    +
    +def _decode_manifest(value: bytes) -> Manifest:
    +    try:
    +        envelope = json.loads(value)
    +        if envelope["format_version"] != 1:
    +            raise CorruptionError("unsupported manifest format")
    +        payload = envelope["payload"]
    +        if hashlib.sha256(_canonical_json(payload)).hexdigest() != envelope["sha256"]:
    +            raise CorruptionError("manifest checksum mismatch")
    +        return Manifest(
    +            generation=int(payload["generation"]),
    +            schema_fingerprint=str(payload["schema_fingerprint"]),
    +            segment_ids=tuple(payload["segment_ids"]),
    +            replay_boundary=int(payload["replay_boundary"]),
    +        )
    +    except CorruptionError:
    +        raise
    +    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
    +        raise CorruptionError("invalid manifest") from error
    +
    +
    +def _canonical_json(value: object) -> bytes:
    +    return json.dumps(
    +        value,
    +        ensure_ascii=False,
    +        allow_nan=False,
    +        sort_keys=True,
    +        separators=(",", ":"),
    +    ).encode()
    +
    +
    +def _write_fsynced(path: Path, value: bytes) -> None:
    +    with path.open("xb") as stream:
    +        stream.write(value)
    +        stream.flush()
    +        os.fsync(stream.fileno())
    +
    ```

??? note "File diff: src/miniqdrant/persistence/metadata.py"
    ```diff
    diff --git a/src/miniqdrant/persistence/metadata.py b/src/miniqdrant/persistence/metadata.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..753b791839165f6ff073cdc04cb0e833d05d1e93
    --- /dev/null
    +++ b/src/miniqdrant/persistence/metadata.py
    @@ -0,0 +1,75 @@
    +from __future__ import annotations
    +
    +import hashlib
    +import json
    +import os
    +from dataclasses import dataclass
    +from pathlib import Path
    +
    +from miniqdrant.config import CollectionConfig, config_from_dict, config_to_dict
    +from miniqdrant.errors import CorruptionError
    +from miniqdrant.filters.index import PayloadSchema
    +from miniqdrant.persistence.fsync import fsync_directory
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class CollectionMetadata:
    +    name: str
    +    config: CollectionConfig
    +    payload_schemas: dict[str, PayloadSchema]
    +
    +
    +def write_collection_metadata(path: Path, metadata: CollectionMetadata) -> None:
    +    payload = {
    +        "name": metadata.name,
    +        "config": config_to_dict(metadata.config),
    +        "payload_schemas": {
    +            field: schema.value
    +            for field, schema in sorted(metadata.payload_schemas.items())
    +        },
    +    }
    +    canonical = _canonical_json(payload)
    +    envelope = {
    +        "format_version": 1,
    +        "payload": payload,
    +        "sha256": hashlib.sha256(canonical).hexdigest(),
    +    }
    +    temporary = path.with_suffix(".json.tmp")
    +    with temporary.open("wb") as stream:
    +        stream.write(_canonical_json(envelope))
    +        stream.flush()
    +        os.fsync(stream.fileno())
    +    os.replace(temporary, path)
    +    fsync_directory(path.parent)
    +
    +
    +def read_collection_metadata(path: Path) -> CollectionMetadata:
    +    try:
    +        envelope = json.loads(path.read_bytes())
    +        if envelope["format_version"] != 1:
    +            raise CorruptionError("unsupported collection metadata format")
    +        payload = envelope["payload"]
    +        if hashlib.sha256(_canonical_json(payload)).hexdigest() != envelope["sha256"]:
    +            raise CorruptionError("collection metadata checksum mismatch")
    +        return CollectionMetadata(
    +            name=str(payload["name"]),
    +            config=config_from_dict(payload["config"]),
    +            payload_schemas={
    +                field: PayloadSchema(schema)
    +                for field, schema in payload["payload_schemas"].items()
    +            },
    +        )
    +    except CorruptionError:
    +        raise
    +    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as error:
    +        raise CorruptionError(f"invalid collection metadata: {path}") from error
    +
    +
    +def _canonical_json(value: object) -> bytes:
    +    return json.dumps(
    +        value,
    +        ensure_ascii=False,
    +        allow_nan=False,
    +        sort_keys=True,
    +        separators=(",", ":"),
    +    ).encode()
    ```

??? note "File diff: src/miniqdrant/segment/codec.py"
    ```diff
    diff --git a/src/miniqdrant/segment/codec.py b/src/miniqdrant/segment/codec.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..386a7c6099e3929e5a6b6c855434d2cfc6383ff9
    --- /dev/null
    +++ b/src/miniqdrant/segment/codec.py
    @@ -0,0 +1,329 @@
    +from __future__ import annotations
    +
    +import hashlib
    +import json
    +import os
    +import shutil
    +import struct
    +import tempfile
    +import zlib
    +from collections.abc import Iterable, Mapping
    +from dataclasses import dataclass
    +from pathlib import Path
    +from uuid import UUID
    +
    +from miniqdrant.config import (
    +    CollectionConfig,
    +    config_from_dict,
    +    config_to_dict,
    +)
    +from miniqdrant.errors import CorruptionError
    +from miniqdrant.filters.index import PayloadSchema
    +from miniqdrant.ids import PointId, canonicalize_point_id, point_id_sort_key
    +from miniqdrant.index.hnsw import HnswGraph, HnswIndex
    +from miniqdrant.json_values import freeze_json_object, thaw_json
    +from miniqdrant.models import StoredPoint
    +from miniqdrant.persistence.fsync import fsync_directory
    +from miniqdrant.segment.immutable import ImmutableSegment
    +
    +_MAGIC = b"MQSG"
    +_VERSION = 1
    +_HEADER = struct.Struct(">4sBI")
    +_CRC = struct.Struct(">I")
    +_FILES = (
    +    "points.bin",
    +    "payloads.bin",
    +    "versions.bin",
    +    "deleted.bin",
    +    "hnsw.bin",
    +    "payload-indexes.bin",
    +)
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class SegmentImage:
    +    segment_id: str
    +    config: CollectionConfig
    +    records: tuple[StoredPoint, ...]
    +    payload_schemas: Mapping[str, PayloadSchema]
    +    indexed: bool
    +    hnsw_graph: HnswGraph | None
    +
    +    @classmethod
    +    def build(
    +        cls,
    +        *,
    +        segment_id: str,
    +        config: CollectionConfig,
    +        records: Iterable[StoredPoint],
    +        payload_schemas: Mapping[str, PayloadSchema],
    +        indexed: bool,
    +    ) -> SegmentImage:
    +        ordered = tuple(sorted(records, key=lambda point: point_id_sort_key(point.id)))
    +        live = tuple(point for point in ordered if not point.deleted)
    +        graph = (
    +            HnswIndex.build(live, distance=config.distance, config=config.hnsw).export_graph()
    +            if indexed and live
    +            else None
    +        )
    +        return cls(
    +            segment_id,
    +            config,
    +            ordered,
    +            dict(payload_schemas),
    +            indexed,
    +            graph,
    +        )
    +
    +    def to_segment(self) -> ImmutableSegment:
    +        return ImmutableSegment.build(
    +            self.config,
    +            self.records,
    +            payload_schemas=self.payload_schemas,
    +            indexed=self.indexed,
    +        )
    +
    +    def semantic_fingerprint(self) -> str:
    +        payload = {
    +            "segment_id": self.segment_id,
    +            "config": config_to_dict(self.config),
    +            "records": [_encode_record(record) for record in self.records],
    +            "payload_schemas": {
    +                path: schema.value for path, schema in sorted(self.payload_schemas.items())
    +            },
    +            "indexed": self.indexed,
    +            "hnsw": _encode_graph(self.hnsw_graph),
    +        }
    +        return hashlib.sha256(_canonical_json(payload)).hexdigest()
    +
    +
    +class SegmentCodec:
    +    @staticmethod
    +    def write_atomic(root: str | Path, image: SegmentImage) -> Path:
    +        directory = Path(root)
    +        directory.mkdir(parents=True, exist_ok=True)
    +        target = directory / image.segment_id
    +        if target.exists():
    +            raise FileExistsError(target)
    +        temporary = Path(tempfile.mkdtemp(prefix=f".{image.segment_id}-", dir=directory))
    +        try:
    +            payloads = _image_files(image)
    +            checksums: dict[str, str] = {}
    +            for filename, payload in payloads.items():
    +                path = temporary / filename
    +                encoded = _encode_blob(payload)
    +                _write_fsynced(path, encoded)
    +                checksums[filename] = hashlib.sha256(encoded).hexdigest()
    +            meta = {
    +                "format_version": _VERSION,
    +                "segment_id": image.segment_id,
    +                "config": config_to_dict(image.config),
    +                "indexed": image.indexed,
    +                "checksums": checksums,
    +            }
    +            _write_fsynced(temporary / "meta.json", _canonical_json(meta))
    +            fsync_directory(temporary)
    +            os.replace(temporary, target)
    +            fsync_directory(directory)
    +            return target
    +        except BaseException:
    +            if temporary.exists():
    +                shutil.rmtree(temporary)
    +            raise
    +
    +    @staticmethod
    +    def read(path: str | Path) -> SegmentImage:
    +        directory = Path(path)
    +        try:
    +            meta = json.loads((directory / "meta.json").read_bytes())
    +            if meta["format_version"] != _VERSION:
    +                raise CorruptionError("unsupported segment format version")
    +            checksums = meta["checksums"]
    +            payloads: dict[str, object] = {}
    +            for filename in _FILES:
    +                encoded = (directory / filename).read_bytes()
    +                if hashlib.sha256(encoded).hexdigest() != checksums[filename]:
    +                    raise CorruptionError(f"segment checksum mismatch: {filename}")
    +                payloads[filename] = _decode_blob(encoded)
    +            return _decode_image(meta, payloads)
    +        except CorruptionError:
    +            raise
    +        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as error:
    +            raise CorruptionError(f"invalid segment at {directory}") from error
    +
    +
    +def _image_files(image: SegmentImage) -> dict[str, object]:
    +    records = image.records
    +    return {
    +        "points.bin": [
    +            {"id": _encode_id(point.id), "vector": list(point.vector)}
    +            for point in records
    +            if not point.deleted
    +        ],
    +        "payloads.bin": [
    +            {"id": _encode_id(point.id), "payload": thaw_json(point.payload)}
    +            for point in records
    +            if not point.deleted
    +        ],
    +        "versions.bin": [
    +            {"id": _encode_id(point.id), "version": point.version} for point in records
    +        ],
    +        "deleted.bin": [
    +            _encode_id(point.id) for point in records if point.deleted
    +        ],
    +        "hnsw.bin": _encode_graph(image.hnsw_graph),
    +        "payload-indexes.bin": {
    +            path: schema.value for path, schema in sorted(image.payload_schemas.items())
    +        },
    +    }
    +
    +
    +def _decode_image(meta: dict[str, object], payloads: dict[str, object]) -> SegmentImage:
    +    point_values = {
    +        _decode_id(item["id"]): tuple(item["vector"])
    +        for item in payloads["points.bin"]
    +    }
    +    payload_values = {
    +        _decode_id(item["id"]): freeze_json_object(item["payload"])
    +        for item in payloads["payloads.bin"]
    +    }
    +    deleted = {_decode_id(value) for value in payloads["deleted.bin"]}
    +    records = tuple(
    +        StoredPoint(
    +            id=(point_id := _decode_id(item["id"])),
    +            vector=() if point_id in deleted else point_values[point_id],
    +            payload=freeze_json_object({}) if point_id in deleted else payload_values[point_id],
    +            version=int(item["version"]),
    +            deleted=point_id in deleted,
    +        )
    +        for item in payloads["versions.bin"]
    +    )
    +    schemas = {
    +        path: PayloadSchema(schema)
    +        for path, schema in payloads["payload-indexes.bin"].items()
    +    }
    +    return SegmentImage(
    +        segment_id=str(meta["segment_id"]),
    +        config=config_from_dict(meta["config"]),
    +        records=records,
    +        payload_schemas=schemas,
    +        indexed=bool(meta["indexed"]),
    +        hnsw_graph=_decode_graph(payloads["hnsw.bin"]),
    +    )
    +
    +
    +def _encode_blob(value: object) -> bytes:
    +    payload = _canonical_json(value)
    +    body = _HEADER.pack(_MAGIC, _VERSION, len(payload)) + payload
    +    return body + _CRC.pack(zlib.crc32(body))
    +
    +
    +def _decode_blob(value: bytes) -> object:
    +    if len(value) < _HEADER.size + _CRC.size:
    +        raise CorruptionError("segment blob is truncated")
    +    magic, version, length = _HEADER.unpack_from(value)
    +    expected_length = _HEADER.size + length + _CRC.size
    +    if magic != _MAGIC or version != _VERSION or len(value) != expected_length:
    +        raise CorruptionError("invalid segment blob header")
    +    body = value[: _HEADER.size + length]
    +    expected_crc = _CRC.unpack_from(value, _HEADER.size + length)[0]
    +    if zlib.crc32(body) != expected_crc:
    +        raise CorruptionError("segment blob checksum mismatch")
    +    try:
    +        return json.loads(value[_HEADER.size : _HEADER.size + length])
    +    except (UnicodeDecodeError, json.JSONDecodeError) as error:
    +        raise CorruptionError("invalid segment blob JSON") from error
    +
    +
    +def _encode_record(record: StoredPoint) -> dict[str, object]:
    +    return {
    +        "id": _encode_id(record.id),
    +        "vector": list(record.vector),
    +        "payload": thaw_json(record.payload),
    +        "version": record.version,
    +        "deleted": record.deleted,
    +    }
    +
    +
    +def _encode_graph(graph: HnswGraph | None) -> object:
    +    if graph is None:
    +        return None
    +    return {
    +        "entry_point": None if graph.entry_point is None else _encode_id(graph.entry_point),
    +        "max_level": graph.max_level,
    +        "levels": [
    +            [_encode_id(point_id), level]
    +            for point_id, level in sorted(
    +                graph.levels.items(),
    +                key=lambda item: point_id_sort_key(item[0]),
    +            )
    +        ],
    +        "layers": [
    +            [
    +                layer,
    +                [
    +                    [
    +                        _encode_id(point_id),
    +                        [_encode_id(neighbor) for neighbor in neighbors],
    +                    ]
    +                    for point_id, neighbors in adjacency.items()
    +                ],
    +            ]
    +            for layer, adjacency in graph.layers.items()
    +        ],
    +    }
    +
    +
    +def _decode_graph(value: object) -> HnswGraph | None:
    +    if value is None:
    +        return None
    +    if not isinstance(value, dict):
    +        raise ValueError("HNSW graph must be an object")
    +    levels = {_decode_id(item[0]): int(item[1]) for item in value["levels"]}
    +    layers = {
    +        int(layer): {
    +            _decode_id(item[0]): tuple(_decode_id(neighbor) for neighbor in item[1])
    +            for item in adjacency
    +        }
    +        for layer, adjacency in value["layers"]
    +    }
    +    entry = value["entry_point"]
    +    return HnswGraph(
    +        entry_point=None if entry is None else _decode_id(entry),
    +        max_level=int(value["max_level"]),
    +        levels=levels,
    +        layers=layers,
    +    )
    +
    +
    +def _encode_id(value: PointId) -> dict[str, object]:
    +    if isinstance(value, int):
    +        return {"kind": "int", "value": value}
    +    return {"kind": "uuid", "value": str(value)}
    +
    +
    +def _decode_id(value: object) -> PointId:
    +    if not isinstance(value, dict):
    +        raise ValueError("point id must be an object")
    +    if value.get("kind") == "int":
    +        return canonicalize_point_id(value.get("value"))
    +    if value.get("kind") == "uuid":
    +        return UUID(str(value.get("value")))
    +    raise ValueError("unknown point id encoding")
    +
    +
    +def _canonical_json(value: object) -> bytes:
    +    return json.dumps(
    +        value,
    +        ensure_ascii=False,
    +        allow_nan=False,
    +        sort_keys=True,
    +        separators=(",", ":"),
    +    ).encode("utf-8")
    +
    +
    +def _write_fsynced(path: Path, value: bytes) -> None:
    +    with path.open("xb") as stream:
    +        stream.write(value)
    +        stream.flush()
    +        os.fsync(stream.fileno())
    ```

??? note "File diff: src/miniqdrant/segment/immutable.py"
    ```diff
    diff --git a/src/miniqdrant/segment/immutable.py b/src/miniqdrant/segment/immutable.py
    index 963da13058e16a61860621032e6ff85d657dcd5d..06bd26e2bc6844e9d1f3d0700f15c3503d835658 100644
    --- a/src/miniqdrant/segment/immutable.py
    +++ b/src/miniqdrant/segment/immutable.py
    @@ -11,6 +11,7 @@ from miniqdrant.index.plain import PlainVectorIndex
     from miniqdrant.models import StoredPoint, normalize_cosine, validate_vector
     from miniqdrant.query.planner import QueryPlanner, SegmentFacts, Strategy
     from miniqdrant.segment.base import (
    +    ScoredCandidate,
         SegmentSearchRequest,
         SegmentSearchResult,
     )
    @@ -88,6 +89,16 @@ class ImmutableSegment:
         def create_payload_index(self, path: str, schema: PayloadSchema) -> None:
             self._payload_indexes.create(path, schema, self.iter_live())

    +    def search_exact(
    +        self,
    +        query: tuple[float, ...],
    +        *,
    +        limit: int,
    +    ) -> tuple[ScoredCandidate, ...]:
    +        return self.search(
    +            SegmentSearchRequest(query, limit, exact=True)
    +        ).candidates
    +
         def search(self, request: SegmentSearchRequest) -> SegmentSearchResult:
             query = validate_vector(request.vector, self._config.dimension)
             if self._config.distance is Distance.COSINE:
    ```

**What it is and why it appears**

The central mechanism is manifest publication and recovery. Segment files, collection metadata, manifest generations, and wal replay need one restart protocol with an atomic publication point.

**Runtime role**

restart opens one complete manifest generation then replays only the ordered WAL suffix not already represented by it.

**Statement understanding**

The durable boundary is this: restart opens one complete manifest generation then replays only the ordered WAL suffix not already represented by it.

#### Package, fixture, and project support

Keep exports, test corpora, dependencies, and the runtime environment reproducible.

??? note "Supporting file diffs (2 files)"
    **`src/miniqdrant/__init__.py`**

    ```diff
    diff --git a/src/miniqdrant/__init__.py b/src/miniqdrant/__init__.py
    index d6ac8d3b970a3a1d0d69a0501b7b10e82dd28bbc..c7564a791db231a7ac47bcf2ba3f57f926049d6c 100644
    --- a/src/miniqdrant/__init__.py
    +++ b/src/miniqdrant/__init__.py
    @@ -30,6 +30,7 @@ from miniqdrant.filters import (
         matches_filter,
     )
     from miniqdrant.models import Point, SearchHit, SearchRequest, SearchResult, StoredPoint
    +from miniqdrant.persistence import Durability
     from miniqdrant.segment import MutableSegment, SegmentSearchRequest
     from miniqdrant.topk import Candidate, TopK

    @@ -44,6 +45,7 @@ __all__ = [
         "CorruptionError",
         "Database",
         "Distance",
    +    "Durability",
         "Filter",
         "HasId",
         "HnswConfig",
    ```

    **`src/miniqdrant/persistence/__init__.py`**

    ```diff
    diff --git a/src/miniqdrant/persistence/__init__.py b/src/miniqdrant/persistence/__init__.py
    index a7e620c7be69e5671aa70e72f14fa064c3555d1b..920448aafe61b9f6157a0db025e00bc9f6ff5e19 100644
    --- a/src/miniqdrant/persistence/__init__.py
    +++ b/src/miniqdrant/persistence/__init__.py
    @@ -1,3 +1,4 @@
    +from miniqdrant.persistence.manifest import Manifest, ManifestStore
     from miniqdrant.persistence.wal import (
         DeleteOperation,
         Durability,
    @@ -10,9 +11,10 @@ from miniqdrant.persistence.wal import (
     __all__ = [
         "DeleteOperation",
         "Durability",
    +    "Manifest",
    +    "ManifestStore",
         "Operation",
         "UpsertOperation",
         "Wal",
         "WalRecord",
     ]
    -
    ```


### Verification evidence

Run `uv run pytest -q $(cat journey/stages/10-manifest-recovery/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: restart opens one complete manifest generation then replays only the ordered WAL suffix not already represented by it.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 3](https://github.com/system-in-miniature/mini-qdrant/blob/main/docs/tutorial/03-wal-manifest.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-qdrant/blob/main/journey/stages/10-manifest-recovery/stage.patch)
