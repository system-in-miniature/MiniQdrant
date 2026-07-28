# MiniQdrant Reference Project Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. This repository is explicitly configured for inline execution; do not dispatch subagents.

**Goal:** Build and verify a direct-first single-node vector database that joins exact/HNSW retrieval, payload filtering and planning, durable versioned segments, online optimization, quantization, snapshots, and crash recovery.

**Architecture:** One `Collection` serializes updates and publishes immutable `CollectionView` values for lock-free distance work. Mutations are validated before versioned WAL append and apply to an appendable segment; exact and optimized immutable segments share one search contract, while a per-segment planner selects exact, indexed-filter, HNSW, or quantized-rescore execution. Immutable manifests form restart roots and optimizers publish replacement segments atomically without overwriting later versions.

**Tech Stack:** Python 3.12, standard-library runtime, pytest, pytest-asyncio only if needed, ruff, custom versioned binary codecs, deterministic clocks/random seeds/failure gates.

---

## 1. Planned file structure

```text
MiniQdrant/
├── pyproject.toml
├── README.md
├── ARCHITECTURE.md
├── DIFFERENCES_FROM_QDRANT.md
├── docs/
│   ├── behavior-matrix.md
│   ├── storage-format.md
│   └── superpowers/
├── src/miniqdrant/
│   ├── __init__.py
│   ├── cli.py
│   ├── config.py
│   ├── errors.py
│   ├── ids.py
│   ├── json_values.py
│   ├── models.py
│   ├── metrics.py
│   ├── topk.py
│   ├── collection.py
│   ├── database.py
│   ├── lifecycle.py
│   ├── filters/
│   │   ├── ast.py
│   │   ├── evaluate.py
│   │   ├── index.py
│   │   └── cardinality.py
│   ├── index/
│   │   ├── plain.py
│   │   ├── hnsw.py
│   │   └── quantization.py
│   ├── query/
│   │   ├── planner.py
│   │   └── executor.py
│   ├── segment/
│   │   ├── base.py
│   │   ├── mutable.py
│   │   ├── immutable.py
│   │   ├── codec.py
│   │   ├── builder.py
│   │   ├── set.py
│   │   └── references.py
│   ├── persistence/
│   │   ├── frame.py
│   │   ├── wal.py
│   │   ├── manifest.py
│   │   ├── fsync.py
│   │   └── snapshot.py
│   ├── optimizer/
│   │   ├── policy.py
│   │   ├── optimizer.py
│   │   └── failures.py
│   └── labs/
│       ├── recall.py
│       ├── filtering.py
│       ├── segments.py
│       └── recovery.py
├── tests/
│   ├── unit/
│   ├── contract/
│   ├── index/
│   ├── query/
│   ├── storage/
│   ├── reliability/
│   ├── concurrency/
│   └── acceptance/
└── tools/count_sloc.py
```

Each module has one semantic owner. `collection.py` coordinates components but
does not implement distance, filtering, graph traversal, or file codecs.

## Task 1: Project scaffold and immutable domain values

**Files:**
- Create: `pyproject.toml`
- Create: `src/miniqdrant/__init__.py`
- Create: `src/miniqdrant/config.py`
- Create: `src/miniqdrant/errors.py`
- Create: `src/miniqdrant/ids.py`
- Create: `src/miniqdrant/json_values.py`
- Create: `src/miniqdrant/models.py`
- Create: `tests/unit/test_domain.py`
- Create: `tests/test_project_contract.py`

- [ ] **Step 1: Write failing project and domain tests**

```python
def test_cosine_point_is_normalized_once():
    config = CollectionConfig(dimension=2, distance=Distance.COSINE)
    point = validate_point(Point(1, (3.0, 4.0), {"kind": "book"}), config)
    assert point.vector == pytest.approx((0.6, 0.8))

def test_non_finite_vector_and_payload_are_rejected():
    config = CollectionConfig(dimension=1, distance=Distance.DOT)
    with pytest.raises(InvalidVectorError):
        validate_point(Point(1, (float("nan"),), {}), config)
    with pytest.raises(InvalidPointError):
        validate_point(Point(1, (1.0,), {"bad": float("inf")}), config)
```

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run pytest tests/unit/test_domain.py tests/test_project_contract.py -q`  
Expected: collection fails because package modules do not exist.

- [ ] **Step 3: Implement the scaffold and validation boundary**

Define frozen `CollectionConfig`, `HnswConfig`, `OptimizerConfig`,
`ScalarQuantizationConfig`, `Point`, `StoredPoint`, `SearchRequest`,
`SearchHit`, and `SearchResult`. Implement:

```python
def validate_point(point: Point, config: CollectionConfig) -> StoredPoint:
    point_id = canonicalize_point_id(point.id)
    vector = validate_vector(point.vector, config.dimension)
    if config.distance is Distance.COSINE:
        vector = normalize_cosine(vector)
    payload = freeze_json_object(point.payload)
    return StoredPoint(point_id, vector, payload, version=0, deleted=False)
```

Use Python 3.12, hatchling, src layout, ruff, pytest, and a standard-library
runtime. Export the stable public types from `miniqdrant.__init__`.

- [ ] **Step 4: Run focused verification**

Run: `uv run ruff check src tests && uv run pytest tests/unit/test_domain.py tests/test_project_contract.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src tests
git commit -m "feat: establish MiniQdrant domain contracts"
```

## Task 2: Distance metrics and deterministic bounded Top-K

**Files:**
- Create: `src/miniqdrant/metrics.py`
- Create: `src/miniqdrant/topk.py`
- Create: `tests/unit/test_metrics.py`
- Create: `tests/unit/test_topk.py`

- [ ] **Step 1: Write failing metric and tie-breaking tests**

```python
@pytest.mark.parametrize(
    ("distance", "expected"),
    [
        (Distance.DOT, 11.0),
        (Distance.COSINE, 1.0),
        (Distance.EUCLID, -8.0),
    ],
)
def test_higher_score_is_always_better(distance, expected):
    assert score(distance, (1.0, 2.0), (3.0, 4.0)) == pytest.approx(expected)

def test_topk_breaks_equal_scores_by_canonical_id():
    collector = TopK(2)
    collector.offer(2, 1.0)
    collector.offer(1, 1.0)
    collector.offer(3, 0.5)
    assert [candidate.point_id for candidate in collector.results()] == [1, 2]
```

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/unit/test_metrics.py tests/unit/test_topk.py -q`  
Expected: imports fail.

- [ ] **Step 3: Implement metrics and heap**

```python
def score(distance: Distance, left: Vector, right: Vector) -> float:
    if distance in (Distance.DOT, Distance.COSINE):
        return math.fsum(a * b for a, b in zip(left, right, strict=True))
    return -math.fsum((a - b) ** 2 for a, b in zip(left, right, strict=True))
```

`TopK` retains at most K candidates and returns `(-score, point_id_sort_key)`
ordering without using point IDs as vector-internal offsets.

- [ ] **Step 4: Verify GREEN and commit**

Run: `uv run pytest tests/unit/test_metrics.py tests/unit/test_topk.py -q`  
Expected: PASS.

```bash
git add src/miniqdrant/metrics.py src/miniqdrant/topk.py tests/unit
git commit -m "feat: add deterministic vector scoring"
```

## Task 3: Payload filter AST and exact evaluation

**Files:**
- Create: `src/miniqdrant/filters/__init__.py`
- Create: `src/miniqdrant/filters/ast.py`
- Create: `src/miniqdrant/filters/evaluate.py`
- Create: `tests/contract/test_filters.py`

- [ ] **Step 1: Write failing nested-filter tests**

```python
def test_boolean_filter_and_array_any_semantics():
    payload = {"kind": "book", "price": 12.0, "tags": ["python", "db"]}
    condition = Filter(
        must=(Match("kind", "book"), Range("price", lte=20)),
        should=(Match("tags", "python"), Match("tags", "rust")),
        must_not=(Match("kind", "movie"),),
    )
    assert matches_filter(1, payload, condition)

def test_missing_path_does_not_match_range():
    assert not matches_filter(1, {}, Filter(must=(Range("price", gte=1),)))
```

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/contract/test_filters.py -q`  
Expected: imports fail.

- [ ] **Step 3: Implement a closed validated AST**

Implement frozen `Match`, `Range`, `HasId`, and recursive `Filter`. Resolve dot
paths through objects and flatten one array level into candidate scalar values.
Reject empty paths, non-finite range bounds, incomparable bound types, and an
empty `should` semantic ambiguity.

```python
def matches_filter(point_id, payload, filter_):
    return (
        all(matches_condition(point_id, payload, item) for item in filter_.must)
        and not any(matches_condition(point_id, payload, item) for item in filter_.must_not)
        and (
            not filter_.should
            or any(matches_condition(point_id, payload, item) for item in filter_.should)
        )
    )
```

- [ ] **Step 4: Verify GREEN and commit**

Run: `uv run pytest tests/contract/test_filters.py -q`  
Expected: PASS.

```bash
git add src/miniqdrant/filters tests/contract/test_filters.py
git commit -m "feat: evaluate structured payload filters"
```

## Task 4: Mutable segment and exact search oracle

**Files:**
- Create: `src/miniqdrant/segment/__init__.py`
- Create: `src/miniqdrant/segment/base.py`
- Create: `src/miniqdrant/segment/mutable.py`
- Create: `src/miniqdrant/index/__init__.py`
- Create: `src/miniqdrant/index/plain.py`
- Create: `tests/index/test_plain.py`
- Create: `tests/contract/test_mutable_segment.py`

- [ ] **Step 1: Write failing exact-search and version tests**

```python
def test_exact_search_obeys_filter_and_topk(config):
    segment = MutableSegment(config)
    segment.apply_upsert(point(1, (1, 0), kind="book"), version=1)
    segment.apply_upsert(point(2, (0.9, 0.1), kind="movie"), version=2)
    hits = segment.search(query=(1, 0), limit=10, filter_=book_filter(), exact=True)
    assert [hit.point_id for hit in hits] == [1]

def test_stale_version_cannot_resurrect_deleted_point(config):
    segment = MutableSegment(config)
    segment.apply_upsert(point(1, (1, 0)), version=4)
    segment.apply_delete(1, version=5)
    segment.apply_upsert(point(1, (0, 1)), version=3)
    assert segment.get(1) is None
```

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/index/test_plain.py tests/contract/test_mutable_segment.py -q`  
Expected: imports fail.

- [ ] **Step 3: Implement segment contracts and plain index**

Define `PointRecord`, `ScoredCandidate`, `SegmentSearchRequest`,
`SegmentSnapshot`, and the `Segment` protocol. `MutableSegment` stores one
highest-version record per external ID. `PlainVectorIndex.search` scans the
provided live IDs, applies the residual filter, and uses `TopK`.

- [ ] **Step 4: Verify GREEN and commit**

Run: `uv run pytest tests/index/test_plain.py tests/contract/test_mutable_segment.py -q`  
Expected: PASS.

```bash
git add src/miniqdrant/index src/miniqdrant/segment tests/index tests/contract
git commit -m "feat: add exact mutable vector segment"
```

## Task 5: Direct collection API and batch atomicity

**Files:**
- Create: `src/miniqdrant/collection.py`
- Create: `src/miniqdrant/database.py`
- Create: `src/miniqdrant/lifecycle.py`
- Create: `tests/contract/test_collection.py`
- Create: `tests/acceptance/test_exact_collection.py`

- [ ] **Step 1: Write failing direct API tests**

```python
def test_invalid_batch_does_not_partially_apply(tmp_path):
    collection = create_collection(tmp_path, dimension=2)
    with pytest.raises(InvalidVectorError):
        collection.upsert([Point(1, (1, 0), {}), Point(2, (1,), {})])
    assert collection.count() == 0

def test_upsert_delete_retrieve_and_search(tmp_path):
    collection = create_collection(tmp_path, dimension=2)
    collection.upsert([Point(1, (1, 0), {"kind": "book"})])
    assert collection.retrieve([1])[0].id == 1
    assert collection.search(SearchRequest((1, 0), 1)).hits[0].id == 1
    collection.delete([1])
    assert collection.retrieve([1]) == ()
```

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/contract/test_collection.py tests/acceptance/test_exact_collection.py -q`  
Expected: imports or API calls fail.

- [ ] **Step 3: Implement synchronous visible-after-return API**

`Collection` validates complete batches, assigns increasing in-memory versions,
applies them under one update lock, captures an immutable read view, and merges
segment candidates. `Database` validates collection names and manages
create/open/drop/close without a network adapter.

- [ ] **Step 4: Verify GREEN and commit**

Run: `uv run pytest tests/contract/test_collection.py tests/acceptance/test_exact_collection.py -q`  
Expected: PASS.

```bash
git add src/miniqdrant/collection.py src/miniqdrant/database.py src/miniqdrant/lifecycle.py tests
git commit -m "feat: expose direct collection operations"
```

## Task 6: Payload indexes, cardinality, and query plans

**Files:**
- Create: `src/miniqdrant/filters/cardinality.py`
- Create: `src/miniqdrant/filters/index.py`
- Create: `src/miniqdrant/query/__init__.py`
- Create: `src/miniqdrant/query/planner.py`
- Create: `src/miniqdrant/query/executor.py`
- Create: `tests/query/test_payload_index.py`
- Create: `tests/query/test_planner.py`
- Create: `tests/query/test_plan_parity.py`

- [ ] **Step 1: Write failing index and strategy tests**

```python
def test_payload_index_candidates_equal_scan(segment):
    segment.create_payload_index("kind", PayloadSchema.KEYWORD)
    condition = Filter(must=(Match("kind", "book"),))
    indexed = segment.payload_indexes.candidates(condition)
    scanned = {p.id for p in segment.iter_live() if matches_filter(p.id, p.payload, condition)}
    assert indexed.ids == scanned

@pytest.mark.parametrize(
    ("count", "filtered", "expected"),
    [
        (10, None, Strategy.EXACT_FULL_SCAN),
        (10_000, 5, Strategy.FILTER_THEN_EXACT),
        (10_000, 8_000, Strategy.FILTERED_HNSW),
        (10_000, None, Strategy.HNSW),
    ],
)
def test_planner_boundaries(count, filtered, expected):
    assert planner.choose(facts(count, filtered)).strategy is expected
```

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/query -q`  
Expected: imports fail.

- [ ] **Step 3: Implement typed indexes and inspectable planning**

Maintain equality maps for keyword/integer/float/bool and sorted `(value, id)`
entries for numeric ranges. Return `CandidateSet(ids, estimate)` only when the
AST can be resolved exactly; otherwise return an estimate plus residual
filter. Implement the five closed strategies and stable reason strings.

- [ ] **Step 4: Verify exact plan parity and commit**

Run: `uv run pytest tests/query -q`  
Expected: PASS and indexed/unindexed exact searches agree.

```bash
git add src/miniqdrant/filters src/miniqdrant/query tests/query
git commit -m "feat: plan filtered vector searches"
```

## Task 7: Deterministic HNSW graph

**Files:**
- Create: `src/miniqdrant/index/hnsw.py`
- Create: `tests/index/test_hnsw_graph.py`
- Create: `tests/index/test_hnsw_search.py`
- Create: `tests/index/test_hnsw_recall.py`

- [ ] **Step 1: Write failing graph/search tests**

```python
def test_same_seed_builds_same_graph(points):
    first = HnswIndex.build(points, metric=Distance.COSINE, seed=7)
    second = HnswIndex.build(points, metric=Distance.COSINE, seed=7)
    assert first.export_graph() == second.export_graph()

def test_hnsw_never_returns_deleted_or_disallowed_point(index):
    index.mark_deleted(3)
    result = index.search((1, 0), limit=10, ef_search=32, allowed_ids={1, 3})
    assert [candidate.point_id for candidate in result] == [1]

def test_recall_improves_to_required_floor(dataset):
    recall = compare_to_exact(dataset, ef_search=64)
    assert recall >= 0.90
```

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/index/test_hnsw_graph.py tests/index/test_hnsw_search.py -q`  
Expected: HNSW is absent.

- [ ] **Step 3: Implement HNSW**

Use stable point-ID bytes plus seed for level generation, bounded neighbor
selection, bidirectional links, upper-level greedy descent, and level-zero
best-first expansion. Track `visited_count` for labs. Traverse nonmatching
nodes but only admit `allowed_ids` to results.

- [ ] **Step 4: Verify invariants and recall**

Run: `uv run pytest tests/index/test_hnsw_graph.py tests/index/test_hnsw_search.py tests/index/test_hnsw_recall.py -q`  
Expected: PASS with deterministic recall floor.

- [ ] **Step 5: Commit**

```bash
git add src/miniqdrant/index/hnsw.py tests/index
git commit -m "feat: add deterministic HNSW retrieval"
```

## Task 8: Immutable segments and HNSW planner integration

**Files:**
- Create: `src/miniqdrant/segment/immutable.py`
- Create: `src/miniqdrant/segment/builder.py`
- Modify: `src/miniqdrant/query/executor.py`
- Modify: `src/miniqdrant/collection.py`
- Create: `tests/query/test_hnsw_plans.py`
- Create: `tests/acceptance/test_cross_segment_search.py`

- [ ] **Step 1: Write failing cross-segment tests**

```python
def test_latest_version_wins_even_when_old_scores_higher(collection):
    collection.upsert([Point(1, (1, 0), {"v": "old"})])
    collection.flush()
    collection.upsert([Point(1, (0, 1), {"v": "new"})])
    hits = collection.search(SearchRequest((1, 0), 10, exact=True)).hits
    assert hits[0].payload["v"] == "new"

def test_delete_overlay_hides_immutable_hnsw_hit(collection):
    collection.upsert([Point(1, (1, 0), {})])
    collection.flush(indexed=True)
    collection.delete([1])
    assert collection.search(SearchRequest((1, 0), 10)).hits == ()
```

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/query/test_hnsw_plans.py tests/acceptance/test_cross_segment_search.py -q`  
Expected: immutable flush path fails.

- [ ] **Step 3: Implement collection-level oversampling and deduplication**

Build immutable segment images containing points, versions, payload indexes,
and optional HNSW. Search each segment with `limit + stale_id_budget`, merge by
external ID and greatest version, honor the collection tombstone/version map,
then exact-rescore and collect final Top-K.

- [ ] **Step 4: Verify GREEN and commit**

Run: `uv run pytest tests/query tests/acceptance/test_cross_segment_search.py -q`  
Expected: PASS.

```bash
git add src/miniqdrant/segment src/miniqdrant/query src/miniqdrant/collection.py tests
git commit -m "feat: search versioned immutable segments"
```

## Task 9: Versioned checksummed WAL

**Files:**
- Create: `src/miniqdrant/persistence/__init__.py`
- Create: `src/miniqdrant/persistence/frame.py`
- Create: `src/miniqdrant/persistence/fsync.py`
- Create: `src/miniqdrant/persistence/wal.py`
- Create: `tests/storage/test_wal_codec.py`
- Create: `tests/reliability/test_wal_tail.py`
- Create: `tests/reliability/test_wal_replay.py`

- [ ] **Step 1: Write failing codec and recovery tests**

```python
def test_wal_round_trip_is_binary_safe(tmp_path):
    wal = Wal.create(tmp_path / "wal", durability=Durability.ALWAYS)
    operation = UpsertOperation((Point(1, (1.0,), {"text": "雪"}),))
    record = wal.append(operation)
    assert list(wal.replay()) == [record]

def test_incomplete_active_tail_is_truncated(tmp_path):
    wal = populated_wal(tmp_path)
    with wal.active_path.open("ab") as stream:
        stream.write(b"\x00\x00\x00")
    reopened = Wal.open(tmp_path / "wal")
    assert [item.sequence for item in reopened.replay()] == [1, 2]
```

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/storage/test_wal_codec.py tests/reliability/test_wal_tail.py -q`  
Expected: persistence modules absent.

- [ ] **Step 3: Implement stable operation encoding**

Use explicit tags, big-endian fixed-width integers, length-prefixed UTF-8/JSON
payloads, canonical JSON separators and key ordering, frame version, and CRC32.
`Wal.append` assigns strictly increasing sequences. Only the active incomplete
tail is recoverably truncated; earlier corruption raises `CorruptionError`.

- [ ] **Step 4: Verify durability policy and replay**

Run: `uv run pytest tests/storage/test_wal_codec.py tests/reliability/test_wal_tail.py tests/reliability/test_wal_replay.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/miniqdrant/persistence tests/storage tests/reliability
git commit -m "feat: persist ordered point operations in WAL"
```

## Task 10: Durable segment codec and atomic manifest

**Files:**
- Create: `src/miniqdrant/segment/codec.py`
- Create: `src/miniqdrant/persistence/manifest.py`
- Modify: `src/miniqdrant/segment/builder.py`
- Create: `tests/storage/test_segment_codec.py`
- Create: `tests/storage/test_manifest.py`
- Create: `tests/reliability/test_manifest_publish.py`

- [ ] **Step 1: Write failing segment/manifest tests**

```python
def test_segment_round_trip_preserves_versions_indexes_and_graph(tmp_path, image):
    path = SegmentCodec.write_atomic(tmp_path, image)
    restored = SegmentCodec.read(path)
    assert restored.semantic_fingerprint() == image.semantic_fingerprint()

def test_failed_current_swap_keeps_old_manifest(tmp_path, failure_gate):
    store = manifest_store_with_generation(tmp_path, 1)
    failure_gate.raise_at("before_current_replace")
    with pytest.raises(InjectedFailure):
        store.publish(manifest(generation=2))
    assert store.load_current().generation == 1
```

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/storage/test_segment_codec.py tests/storage/test_manifest.py tests/reliability/test_manifest_publish.py -q`  
Expected: codec/store absent.

- [ ] **Step 3: Implement custom files and atomic publication**

Write versioned checksummed `points.bin`, `payloads.bin`, `versions.bin`,
`deleted.bin`, `hnsw.bin`, `payload-indexes.bin`, and optional
`quantized.bin`. Fsync files, temporary segment directory, manifest, and parent
directory in order. Replace `CURRENT` only after all referenced files exist.

- [ ] **Step 4: Verify GREEN and commit**

Run: `uv run pytest tests/storage tests/reliability/test_manifest_publish.py -q`  
Expected: PASS.

```bash
git add src/miniqdrant/segment src/miniqdrant/persistence tests/storage tests/reliability
git commit -m "feat: publish durable segment manifests"
```

## Task 11: Flush, reopen, and WAL-boundary recovery

**Files:**
- Modify: `src/miniqdrant/collection.py`
- Modify: `src/miniqdrant/database.py`
- Create: `src/miniqdrant/segment/set.py`
- Create: `tests/reliability/test_restart.py`
- Create: `tests/reliability/test_crash_boundaries.py`
- Create: `tests/acceptance/test_cross_restart.py`

- [ ] **Step 1: Write failing restart tests**

```python
def test_acknowledged_upsert_survives_restart(tmp_path):
    db = create_database(tmp_path, durability=Durability.ALWAYS)
    db.create_collection("items", dimension=2).upsert([Point(1, (1, 0), {})])
    simulate_process_loss(db)
    reopened = Database.open(tmp_path)
    assert reopened.collection("items").retrieve([1])[0].id == 1

def test_crash_after_wal_before_apply_recovers_once(tmp_path, failure_gate):
    collection = durable_collection(tmp_path, failure_gate)
    failure_gate.raise_at("after_wal_fsync")
    with pytest.raises(InjectedFailure):
        collection.upsert([Point(1, (1, 0), {})])
    assert reopen(tmp_path).collection("items").count() == 1
```

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/reliability/test_restart.py tests/reliability/test_crash_boundaries.py -q`  
Expected: restart does not yet restore.

- [ ] **Step 3: Wire mutation, flush, and startup**

Make WAL the source of operation versions. Flush freezes the appendable view,
writes a plain immutable segment, publishes replay boundary, and then permits
WAL truncation. Startup validates the root, reconstructs greatest versions,
replays newer operations idempotently, and opens a fresh appendable segment.

- [ ] **Step 4: Verify restart matrix and commit**

Run: `uv run pytest tests/reliability tests/acceptance/test_cross_restart.py -q`  
Expected: PASS for before/after WAL, segment write, manifest, and CURRENT gates.

```bash
git add src/miniqdrant tests/reliability tests/acceptance
git commit -m "feat: recover collections from manifest and WAL"
```

## Task 12: Online indexing, merge, vacuum, and safe reclamation

**Files:**
- Create: `src/miniqdrant/optimizer/__init__.py`
- Create: `src/miniqdrant/optimizer/policy.py`
- Create: `src/miniqdrant/optimizer/failures.py`
- Create: `src/miniqdrant/optimizer/optimizer.py`
- Create: `src/miniqdrant/segment/references.py`
- Modify: `src/miniqdrant/collection.py`
- Create: `tests/concurrency/test_online_optimize.py`
- Create: `tests/storage/test_merge.py`
- Create: `tests/storage/test_vacuum.py`
- Create: `tests/reliability/test_optimizer_publish.py`

- [ ] **Step 1: Write failing late-write and reader tests**

```python
def test_write_during_build_wins_after_publish(collection, gate):
    collection.upsert([Point(1, (1, 0), {"version": "old"})])
    handle = collection.start_optimize(gate=gate)
    gate.wait_until("sources_captured")
    collection.upsert([Point(1, (0, 1), {"version": "new"})])
    gate.release("finish_build")
    handle.result()
    assert collection.retrieve([1])[0].payload["version"] == "new"

def test_existing_view_can_finish_after_merge(collection):
    old_view = collection.capture_view()
    collection.merge()
    assert old_view.search(SearchRequest((1, 0), 10)).hits
    old_paths = old_view.segment_paths
    old_view.close()
    assert all(not path.exists() for path in old_paths)
```

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/concurrency/test_online_optimize.py tests/storage/test_merge.py -q`  
Expected: optimizer absent.

- [ ] **Step 3: Implement explicit optimizer transitions**

Capture source segments and version V, build outside the publication lock,
discard replacement records whose IDs have a later global version, publish one
new manifest, then retire old paths through reference counts. Implement
indexing, smallest-segment merge, deleted-ratio vacuum, and deterministic
policy selection.

- [ ] **Step 4: Verify failure and concurrency paths**

Run: `uv run pytest tests/concurrency tests/storage/test_merge.py tests/storage/test_vacuum.py tests/reliability/test_optimizer_publish.py -q`  
Expected: PASS with no hidden late write or early deletion.

- [ ] **Step 5: Commit**

```bash
git add src/miniqdrant/optimizer src/miniqdrant/segment src/miniqdrant/collection.py tests
git commit -m "feat: optimize segments without blocking readers"
```

## Task 13: Scalar quantization with exact rescoring

**Files:**
- Create: `src/miniqdrant/index/quantization.py`
- Modify: `src/miniqdrant/segment/builder.py`
- Modify: `src/miniqdrant/query/executor.py`
- Create: `tests/index/test_quantization.py`
- Create: `tests/query/test_quantized_rescore.py`

- [ ] **Step 1: Write failing calibration and recall tests**

```python
def test_int8_round_trip_has_bounded_error(vectors):
    quantizer = ScalarQuantizer.fit(vectors)
    for vector in vectors:
        restored = quantizer.decode(quantizer.encode(vector))
        assert max_abs_error(vector, restored) <= quantizer.max_error_bound

def test_rescore_uses_original_vectors(segment, queries):
    for query in queries:
        result = segment.search_quantized(query, limit=10, oversampling=4)
        expected = segment.search_exact(query, limit=10)
        assert recall_at_k(result, expected) >= 0.95
        assert all(hit.score == exact_score(query, segment.vector(hit.id)) for hit in result)
```

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/index/test_quantization.py tests/query/test_quantized_rescore.py -q`  
Expected: quantization absent.

- [ ] **Step 3: Implement per-dimension int8 quantization**

Store per-dimension minima and scales; constant dimensions use a zero code and
zero scale. Use quantized vectors only for candidate scoring, oversample by a
validated factor, fetch original floats, and exact-rescore final candidates.

- [ ] **Step 4: Verify GREEN and commit**

Run: `uv run pytest tests/index/test_quantization.py tests/query/test_quantized_rescore.py -q`  
Expected: PASS with required recall floor.

```bash
git add src/miniqdrant/index/quantization.py src/miniqdrant/segment src/miniqdrant/query tests
git commit -m "feat: rescore scalar-quantized candidates"
```

## Task 14: Atomic collection snapshots and restore

**Files:**
- Create: `src/miniqdrant/persistence/snapshot.py`
- Modify: `src/miniqdrant/collection.py`
- Modify: `src/miniqdrant/database.py`
- Create: `tests/reliability/test_snapshot.py`
- Create: `tests/reliability/test_snapshot_restore_failure.py`
- Create: `tests/acceptance/test_snapshot_roundtrip.py`

- [ ] **Step 1: Write failing snapshot tests**

```python
def test_snapshot_restores_searchable_collection(tmp_path):
    collection = populated_optimized_collection(tmp_path / "live")
    snapshot = collection.create_snapshot(tmp_path / "backups" / "sp-1")
    Database.restore_collection(snapshot, tmp_path / "restored", "items")
    restored = Database.open(tmp_path / "restored").collection("items")
    assert restored.search(reference_query()).hits == collection.search(reference_query()).hits

def test_invalid_snapshot_never_replaces_live_collection(tmp_path):
    live = populated_collection(tmp_path / "db")
    corrupt_snapshot(tmp_path / "bad")
    with pytest.raises(SnapshotError):
        live.database.restore_collection(tmp_path / "bad", name="items")
    assert live.retrieve([1])
```

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/reliability/test_snapshot.py tests/reliability/test_snapshot_restore_failure.py -q`  
Expected: snapshot API absent.

- [ ] **Step 3: Implement snapshot root and validate-before-replace**

Flush to a committed manifest, copy or hardlink only referenced immutable
files, include required WAL suffix, write checksums, fsync, and rename the
temporary snapshot. Restore into a temporary collection, validate and open it,
then atomically swap the directory.

- [ ] **Step 4: Verify GREEN and commit**

Run: `uv run pytest tests/reliability/test_snapshot.py tests/reliability/test_snapshot_restore_failure.py tests/acceptance/test_snapshot_roundtrip.py -q`  
Expected: PASS.

```bash
git add src/miniqdrant/persistence/snapshot.py src/miniqdrant tests/reliability tests/acceptance
git commit -m "feat: create and restore atomic snapshots"
```

## Task 15: CLI, labs, lifecycle, and documentation

**Files:**
- Create: `src/miniqdrant/cli.py`
- Create: `src/miniqdrant/labs/__init__.py`
- Create: `src/miniqdrant/labs/recall.py`
- Create: `src/miniqdrant/labs/filtering.py`
- Create: `src/miniqdrant/labs/segments.py`
- Create: `src/miniqdrant/labs/recovery.py`
- Create: `tests/acceptance/test_cli.py`
- Create: `tests/acceptance/test_labs.py`
- Create: `tests/contract/test_lifecycle.py`
- Create: `README.md`
- Create: `ARCHITECTURE.md`
- Create: `DIFFERENCES_FROM_QDRANT.md`
- Create: `docs/behavior-matrix.md`
- Create: `docs/storage-format.md`

- [ ] **Step 1: Write failing CLI/lifecycle tests**

```python
def test_cli_create_upsert_search(tmp_path, cli):
    cli("create", str(tmp_path), "items", "--dimension", "2", "--distance", "cosine")
    cli("upsert", str(tmp_path), "items", fixture("points.jsonl"))
    result = cli("search", str(tmp_path), "items", "[1,0]", "--limit", "1")
    assert json.loads(result.stdout)["hits"][0]["id"] == 1

def test_close_is_idempotent_and_rejects_new_work(collection):
    collection.close()
    collection.close()
    with pytest.raises(ClosedResourceError):
        collection.search(SearchRequest((1, 0), 1))
```

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/acceptance/test_cli.py tests/contract/test_lifecycle.py -q`  
Expected: CLI/lifecycle behavior incomplete.

- [ ] **Step 3: Implement thin CLI and deterministic labs**

Use `argparse`. All CLI commands call public `Database`/`Collection` methods.
Labs print JSON metrics with fixed seeds and bounded fixtures. Document exact
versus approximate behavior, acknowledgement boundaries, file formats, failure
experiments, and every deliberate Qdrant difference.

- [ ] **Step 4: Verify examples and docs**

Run:

```bash
uv run miniqdrant --help
uv run pytest tests/acceptance/test_cli.py tests/acceptance/test_labs.py tests/contract/test_lifecycle.py -q
```

Expected: help exits 0 and tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/miniqdrant/cli.py src/miniqdrant/labs tests README.md ARCHITECTURE.md DIFFERENCES_FROM_QDRANT.md docs
git commit -m "docs: publish MiniQdrant reference project"
```

## Task 16: Full acceptance and repository closure

**Files:**
- Create: `tools/__init__.py`
- Create: `tools/count_sloc.py`
- Create: `tests/test_sloc_report.py`
- Create: `tests/acceptance/test_final_acceptance.py`
- Modify: `docs/behavior-matrix.md`
- Modify: `README.md`

- [ ] **Step 1: Add the final behavior matrix test**

```python
def test_full_semantic_closure(tmp_path):
    db = Database.open(tmp_path)
    collection = db.create_collection("items", dimension=4, distance=Distance.COSINE)
    collection.create_payload_index("category", PayloadSchema.KEYWORD)
    collection.upsert(reference_points())
    exact = collection.search(reference_request(exact=True))
    collection.optimize(index=True, quantize=True)
    approximate = collection.search(reference_request(exact=False))
    collection.close()
    reopened = Database.open(tmp_path).collection("items")
    assert reopened.search(reference_request(exact=True)).hits == exact.hits
    assert recall_at_k(approximate.hits, exact.hits) >= 0.90
```

- [ ] **Step 2: Run focused acceptance**

Run: `uv run pytest tests/acceptance -q`  
Expected: PASS.

- [ ] **Step 3: Run complete verification**

Run:

```bash
uv run ruff check .
uv run python -m compileall -q src tests tools
uv run pytest -q
git diff --check
```

Expected: all commands exit 0.

- [ ] **Step 4: Audit requirements against direct evidence**

Update `docs/behavior-matrix.md` so every design goal and invariant names:

```text
public API or module
direct test
failure/recall experiment where applicable
documented Qdrant difference
```

Search for unsupported claims:

```bash
rg -n "production|exactly|compatible|atomic|durable|lossless|no data loss" README.md ARCHITECTURE.md DIFFERENCES_FROM_QDRANT.md docs src
```

Every retained claim must be scoped and proved by the matrix.

- [ ] **Step 5: Verify clean final state and commit**

```bash
uv run ruff check .
uv run pytest -q
git diff --check
git status --short
git add README.md docs tools tests
git commit -m "test: accept complete MiniQdrant project"
git status --short --branch
```

Expected: branch `main`, clean worktree, all tests passing.

