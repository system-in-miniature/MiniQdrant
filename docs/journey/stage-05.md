# Stage 05 · Collection operations

### Goal

Build collection operations and explain its boundary from an executable counterexample, runtime state, and the critical statement.

??? note "Deliverable files"
    - `src/miniqdrant/__init__.py`
    - `src/miniqdrant/collection.py`
    - `src/miniqdrant/database.py`
    - `src/miniqdrant/lifecycle.py`
    - `tests/acceptance/test_exact_collection.py`
    - `tests/contract/test_collection.py`

### The problem at this point

Segments and indexes do not yet form a public database until one collection owns lifecycle, validation, upsert, delete, retrieve, and search.

### Test contract

#### See the failure first

The focused tests force collection operations through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

??? note "File diff: tests/acceptance/test_exact_collection.py"
    ```diff
    diff --git a/tests/acceptance/test_exact_collection.py b/tests/acceptance/test_exact_collection.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..9fa0c8645ac9da2717376ab19b422eb35e34f957
    --- /dev/null
    +++ b/tests/acceptance/test_exact_collection.py
    @@ -0,0 +1,53 @@
    +from __future__ import annotations
    +
    +import pytest
    +
    +from miniqdrant import (
    +    CollectionExistsError,
    +    CollectionNotFoundError,
    +    Database,
    +    Distance,
    +    Filter,
    +    Match,
    +    Point,
    +    SearchRequest,
    +)
    +
    +
    +def test_direct_exact_collection_loop(tmp_path) -> None:
    +    database = Database.open(tmp_path)
    +    collection = database.create_collection("products", dimension=2, distance="cosine")
    +    collection.upsert(
    +        [
    +            Point(1, (1.0, 0.0), {"category": "book"}),
    +            Point(2, (0.8, 0.2), {"category": "movie"}),
    +            Point(3, (0.7, 0.3), {"category": "book"}),
    +        ]
    +    )
    +
    +    result = collection.search(
    +        SearchRequest(
    +            vector=(1.0, 0.0),
    +            limit=2,
    +            filter=Filter(must=(Match("category", "book"),)),
    +            exact=True,
    +        )
    +    )
    +
    +    assert [hit.id for hit in result.hits] == [1, 3]
    +    assert all(hit.payload["category"] == "book" for hit in result.hits)
    +
    +
    +def test_database_collection_ownership(tmp_path) -> None:
    +    database = Database.open(tmp_path)
    +    created = database.create_collection("items", dimension=2, distance=Distance.DOT)
    +
    +    assert database.collection("items") is created
    +    with pytest.raises(CollectionExistsError):
    +        database.create_collection("items", dimension=2, distance=Distance.DOT)
    +
    +    database.drop_collection("items")
    +
    +    with pytest.raises(CollectionNotFoundError):
    +        database.collection("items")
    +
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force collection operations through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert [hit.id for hit in result.hits] == [1, 3]
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

??? note "File diff: tests/contract/test_collection.py"
    ```diff
    diff --git a/tests/contract/test_collection.py b/tests/contract/test_collection.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..dd75b733b69411bb26dd061b543e5ec2fc44cb56
    --- /dev/null
    +++ b/tests/contract/test_collection.py
    @@ -0,0 +1,84 @@
    +from __future__ import annotations
    +
    +import pytest
    +
    +from miniqdrant import (
    +    ClosedResourceError,
    +    Database,
    +    Distance,
    +    InvalidVectorError,
    +    Point,
    +    SearchRequest,
    +)
    +
    +
    +def test_invalid_batch_does_not_partially_apply(tmp_path) -> None:
    +    database = Database.open(tmp_path)
    +    collection = database.create_collection("items", dimension=2, distance=Distance.DOT)
    +
    +    with pytest.raises(InvalidVectorError):
    +        collection.upsert(
    +            [
    +                Point(1, (1.0, 0.0), {}),
    +                Point(2, (1.0,), {}),
    +            ]
    +        )
    +
    +    assert collection.count() == 0
    +    assert collection.retrieve([1, 2]) == ()
    +
    +
    +def test_upsert_delete_retrieve_and_search(tmp_path) -> None:
    +    database = Database.open(tmp_path)
    +    collection = database.create_collection("items", dimension=2, distance=Distance.DOT)
    +
    +    first_version = collection.upsert([Point(1, (1.0, 0.0), {"kind": "book"})])
    +
    +    assert first_version == 1
    +    assert collection.retrieve([1])[0].id == 1
    +    assert collection.search(SearchRequest((1.0, 0.0), 1)).hits[0].id == 1
    +
    +    delete_version = collection.delete([1])
    +
    +    assert delete_version == 2
    +    assert collection.retrieve([1]) == ()
    +    assert collection.search(SearchRequest((1.0, 0.0), 1)).hits == ()
    +
    +
    +def test_search_response_projection_and_threshold(tmp_path) -> None:
    +    collection = Database.open(tmp_path).create_collection(
    +        "items",
    +        dimension=2,
    +        distance=Distance.DOT,
    +    )
    +    collection.upsert([Point(1, (0.5, 0.0), {"kind": "book"})])
    +
    +    omitted = collection.search(
    +        SearchRequest(
    +            (1.0, 0.0),
    +            1,
    +            score_threshold=0.4,
    +            with_payload=False,
    +            with_vector=True,
    +        )
    +    )
    +    excluded = collection.search(SearchRequest((1.0, 0.0), 1, score_threshold=0.6))
    +
    +    assert omitted.hits[0].payload is None
    +    assert omitted.hits[0].vector == (0.5, 0.0)
    +    assert excluded.hits == ()
    +
    +
    +def test_collection_close_is_idempotent_and_rejects_new_work(tmp_path) -> None:
    +    collection = Database.open(tmp_path).create_collection(
    +        "items",
    +        dimension=2,
    +        distance=Distance.DOT,
    +    )
    +
    +    collection.close()
    +    collection.close()
    +
    +    with pytest.raises(ClosedResourceError):
    +        collection.upsert([Point(1, (1.0, 0.0), {})])
    +
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force collection operations through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert [hit.id for hit in result.hits] == [1, 3]
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is collection operations. Segments and indexes do not yet form a public database until one collection owns lifecycle, validation, upsert, delete, retrieve, and search.

### Why this mechanism is necessary

Segments and indexes do not yet form a public database until one collection owns lifecycle, validation, upsert, delete, retrieve, and search. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

public mutations validate completely before publication and reads never expose caller-owned mutable payload state.

### Mechanism blocks

#### Collection operations mechanism

public mutations validate completely before publication and reads never expose caller-owned mutable payload state.

??? note "File diff: src/miniqdrant/collection.py"
    ```diff
    diff --git a/src/miniqdrant/collection.py b/src/miniqdrant/collection.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..59c6856a31775b00db453df146a1a651ae28e4a8
    --- /dev/null
    +++ b/src/miniqdrant/collection.py
    @@ -0,0 +1,143 @@
    +from __future__ import annotations
    +
    +import math
    +from collections.abc import Iterable
    +from pathlib import Path
    +from threading import RLock
    +
    +from miniqdrant.config import CollectionConfig
    +from miniqdrant.errors import InvalidFilterError
    +from miniqdrant.filters import Filter
    +from miniqdrant.ids import PointId, canonicalize_point_id
    +from miniqdrant.lifecycle import Lifecycle
    +from miniqdrant.models import (
    +    Point,
    +    SearchHit,
    +    SearchRequest,
    +    SearchResult,
    +    StoredPoint,
    +    validate_point,
    +)
    +from miniqdrant.segment import MutableSegment, SegmentSearchRequest
    +
    +
    +class Collection(Lifecycle):
    +    def __init__(self, name: str, path: Path, config: CollectionConfig) -> None:
    +        super().__init__()
    +        self._name = name
    +        self._path = path
    +        self._config = config
    +        self._update_lock = RLock()
    +        self._mutable = MutableSegment(config)
    +        self._version = 0
    +
    +    @property
    +    def name(self) -> str:
    +        return self._name
    +
    +    @property
    +    def path(self) -> Path:
    +        return self._path
    +
    +    @property
    +    def config(self) -> CollectionConfig:
    +        return self._config
    +
    +    def count(self) -> int:
    +        self._ensure_open()
    +        with self._update_lock:
    +            return self._mutable.live_count
    +
    +    def upsert(self, points: Iterable[Point]) -> int:
    +        self._ensure_open()
    +        batch = tuple(points)
    +        if not batch:
    +            raise ValueError("upsert batch must not be empty")
    +        for point in batch:
    +            validate_point(point, self._config)
    +        with self._update_lock:
    +            version = self._next_version()
    +            for point in batch:
    +                self._mutable.apply_upsert(point, version)
    +            return version
    +
    +    def delete(self, point_ids: Iterable[object]) -> int:
    +        self._ensure_open()
    +        identifiers = tuple(canonicalize_point_id(item) for item in point_ids)
    +        if not identifiers:
    +            raise ValueError("delete batch must not be empty")
    +        with self._update_lock:
    +            version = self._next_version()
    +            for point_id in identifiers:
    +                self._mutable.apply_delete(point_id, version)
    +            return version
    +
    +    def retrieve(self, point_ids: Iterable[object]) -> tuple[StoredPoint, ...]:
    +        self._ensure_open()
    +        identifiers = tuple(canonicalize_point_id(item) for item in point_ids)
    +        with self._update_lock:
    +            return tuple(
    +                point
    +                for point_id in identifiers
    +                if (point := self._mutable.get(point_id)) is not None
    +            )
    +
    +    def search(self, request: SearchRequest) -> SearchResult:
    +        self._ensure_open()
    +        if request.limit < 1:
    +            raise ValueError("search limit must be positive")
    +        if request.filter is not None and not isinstance(request.filter, Filter):
    +            raise InvalidFilterError("search filter must be a Filter")
    +        if request.score_threshold is not None and not math.isfinite(request.score_threshold):
    +            raise ValueError("score threshold must be finite")
    +        with self._update_lock:
    +            segment_result = self._mutable.search(
    +                SegmentSearchRequest(
    +                    vector=tuple(request.vector),
    +                    limit=request.limit,
    +                    filter=request.filter,
    +                    exact=request.exact,
    +                    ef_search=request.ef_search,
    +                )
    +            )
    +            hits = tuple(
    +                hit
    +                for candidate in segment_result.candidates
    +                if (
    +                    request.score_threshold is None
    +                    or candidate.score >= request.score_threshold
    +                )
    +                if (
    +                    hit := self._project_hit(
    +                        candidate.point_id,
    +                        candidate.score,
    +                        request,
    +                    )
    +                )
    +                is not None
    +            )
    +            return SearchResult(hits, plan=segment_result.strategy)
    +
    +    def close(self) -> None:
    +        self._mark_closed()
    +
    +    def _next_version(self) -> int:
    +        self._version += 1
    +        return self._version
    +
    +    def _project_hit(
    +        self,
    +        point_id: PointId,
    +        score: float,
    +        request: SearchRequest,
    +    ) -> SearchHit | None:
    +        point = self._mutable.get(point_id)
    +        if point is None:
    +            return None
    +        return SearchHit(
    +            id=point.id,
    +            score=score,
    +            payload=point.payload if request.with_payload else None,
    +            vector=point.vector if request.with_vector else None,
    +        )
    +
    ```

??? note "File diff: src/miniqdrant/database.py"
    ```diff
    diff --git a/src/miniqdrant/database.py b/src/miniqdrant/database.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..112ce44dadbd8022b5bf8cec1e72663709d2ef75
    --- /dev/null
    +++ b/src/miniqdrant/database.py
    @@ -0,0 +1,99 @@
    +from __future__ import annotations
    +
    +import re
    +from pathlib import Path
    +from threading import RLock
    +
    +from miniqdrant.collection import Collection
    +from miniqdrant.config import (
    +    CollectionConfig,
    +    Distance,
    +    HnswConfig,
    +    OptimizerConfig,
    +    ScalarQuantizationConfig,
    +)
    +from miniqdrant.errors import (
    +    CollectionExistsError,
    +    CollectionNotFoundError,
    +)
    +from miniqdrant.lifecycle import Lifecycle
    +
    +_COLLECTION_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
    +
    +
    +class Database(Lifecycle):
    +    def __init__(self, path: Path) -> None:
    +        super().__init__()
    +        self._path = path
    +        self._collections_path = path / "collections"
    +        self._collections_path.mkdir(parents=True, exist_ok=True)
    +        self._lock = RLock()
    +        self._collections: dict[str, Collection] = {}
    +
    +    @classmethod
    +    def open(cls, path: str | Path) -> Database:
    +        return cls(Path(path))
    +
    +    @property
    +    def path(self) -> Path:
    +        return self._path
    +
    +    def create_collection(
    +        self,
    +        name: str,
    +        *,
    +        dimension: int,
    +        distance: Distance | str,
    +        hnsw: HnswConfig | None = None,
    +        optimizer: OptimizerConfig | None = None,
    +        quantization: ScalarQuantizationConfig | None = None,
    +    ) -> Collection:
    +        self._ensure_open()
    +        _validate_collection_name(name)
    +        config = CollectionConfig(
    +            dimension=dimension,
    +            distance=Distance(distance),
    +            hnsw=hnsw or HnswConfig(),
    +            optimizer=optimizer or OptimizerConfig(),
    +            quantization=quantization,
    +        )
    +        with self._lock:
    +            if name in self._collections:
    +                raise CollectionExistsError(f"collection already exists: {name}")
    +            path = self._collections_path / name
    +            path.mkdir(parents=True, exist_ok=False)
    +            collection = Collection(name, path, config)
    +            self._collections[name] = collection
    +            return collection
    +
    +    def collection(self, name: str) -> Collection:
    +        self._ensure_open()
    +        with self._lock:
    +            try:
    +                return self._collections[name]
    +            except KeyError as error:
    +                raise CollectionNotFoundError(f"collection not found: {name}") from error
    +
    +    def drop_collection(self, name: str) -> None:
    +        self._ensure_open()
    +        with self._lock:
    +            try:
    +                collection = self._collections.pop(name)
    +            except KeyError as error:
    +                raise CollectionNotFoundError(f"collection not found: {name}") from error
    +            collection.close()
    +
    +    def close(self) -> None:
    +        if not self._mark_closed():
    +            return
    +        with self._lock:
    +            collections = tuple(self._collections.values())
    +            self._collections.clear()
    +        for collection in collections:
    +            collection.close()
    +
    +
    +def _validate_collection_name(name: str) -> None:
    +    if not _COLLECTION_NAME.fullmatch(name):
    +        raise ValueError("collection name must contain only letters, digits, '_' or '-'")
    +
    ```

??? note "File diff: src/miniqdrant/lifecycle.py"
    ```diff
    diff --git a/src/miniqdrant/lifecycle.py b/src/miniqdrant/lifecycle.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..b6be6f9f50777c39b4cfff5cc26407891c17e418
    --- /dev/null
    +++ b/src/miniqdrant/lifecycle.py
    @@ -0,0 +1,28 @@
    +from __future__ import annotations
    +
    +from threading import RLock
    +
    +from miniqdrant.errors import ClosedResourceError
    +
    +
    +class Lifecycle:
    +    def __init__(self) -> None:
    +        self._lifecycle_lock = RLock()
    +        self._closed = False
    +
    +    @property
    +    def closed(self) -> bool:
    +        with self._lifecycle_lock:
    +            return self._closed
    +
    +    def _ensure_open(self) -> None:
    +        if self.closed:
    +            raise ClosedResourceError(f"{type(self).__name__} is closed")
    +
    +    def _mark_closed(self) -> bool:
    +        with self._lifecycle_lock:
    +            if self._closed:
    +                return False
    +            self._closed = True
    +            return True
    +
    ```

**What it is and why it appears**

The central mechanism is collection operations. Segments and indexes do not yet form a public database until one collection owns lifecycle, validation, upsert, delete, retrieve, and search.

**Runtime role**

public mutations validate completely before publication and reads never expose caller-owned mutable payload state.

**Statement understanding**

The durable boundary is this: public mutations validate completely before publication and reads never expose caller-owned mutable payload state.

#### Package, fixture, and project support

Keep exports, test corpora, dependencies, and the runtime environment reproducible.

??? note "Supporting file diffs (1 file)"
    **`src/miniqdrant/__init__.py`**

    ```diff
    diff --git a/src/miniqdrant/__init__.py b/src/miniqdrant/__init__.py
    index e918d4e6e3cfa8f48637faa8959a67ac35adbbde..d57fe02bd682ba9f35a31eb162cd2aaeeb9f84db 100644
    --- a/src/miniqdrant/__init__.py
    +++ b/src/miniqdrant/__init__.py
    @@ -1,3 +1,4 @@
    +from miniqdrant.collection import Collection
     from miniqdrant.config import (
         CollectionConfig,
         Distance,
    @@ -5,6 +6,7 @@ from miniqdrant.config import (
         OptimizerConfig,
         ScalarQuantizationConfig,
     )
    +from miniqdrant.database import Database
     from miniqdrant.errors import (
         ClosedResourceError,
         CollectionExistsError,
    @@ -26,10 +28,12 @@ from miniqdrant.topk import Candidate, TopK
     __all__ = [
         "Candidate",
         "ClosedResourceError",
    +    "Collection",
         "CollectionConfig",
         "CollectionExistsError",
         "CollectionNotFoundError",
         "CorruptionError",
    +    "Database",
         "Distance",
         "Filter",
         "HasId",
    ```


### Verification evidence

Run `uv run pytest -q $(cat journey/stages/05-collection-operations/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: public mutations validate completely before publication and reads never expose caller-owned mutable payload state.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 2](https://github.com/system-in-miniature/mini-qdrant/blob/main/docs/tutorial/02-points-payload.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-qdrant/blob/main/journey/stages/05-collection-operations/stage.patch)
