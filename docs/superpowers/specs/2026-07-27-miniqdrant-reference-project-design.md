# MiniQdrant Reference Project Design

**Date:** 2026-07-27  
**Status:** Approved under delegated final-acceptance authority  
**Repository:** `~/MiniQdrant-workspace/MiniQdrant`  
**Package:** `miniqdrant`  
**CLI:** `miniqdrant`

## 1. Purpose

MiniQdrant is a direct-first Python reference implementation of the mechanisms
that make a vector database useful:

```text
collection schema
→ durable point mutation
→ mutable segment
→ payload indexing and cardinality estimation
→ exact or HNSW candidate generation
→ filtered query planning
→ cross-segment version resolution and Top-K
→ segment optimization and atomic publication
→ snapshot and restart recovery
```

It is not API-compatible with Qdrant and is not a production vector database.
The finished repository is the reference project. Course chapters will be
designed later in a separate repository.

## 2. Chosen scope

Three scopes were considered:

1. **Retrieval kernel only:** exact scan, HNSW, filters, and payload indexes.
   This omits the storage lifecycle that explains how a mutable vector database
   remains searchable while building expensive indexes.
2. **Single-node semantic closure:** retrieval plus point versioning, WAL,
   mutable and immutable segments, query planning, optimization, snapshots,
   recovery, and scalar quantization. This is selected.
3. **Broad Qdrant clone:** add sparse and named vectors, hybrid fusion,
   sharding, replication, consensus, and remote APIs. This is rejected because
   distributed infrastructure and compatibility would displace the distinctive
   single-node mechanisms.

MiniQdrant supports one dense vector per point and one fixed vector schema per
collection. It deliberately excludes sparse vectors, named vectors,
multivectors, full-text retrieval, hybrid fusion, shards, and replicas.

## 3. Product goals

The finished project must let a reader implement, run, and explain:

1. collection-level dimension and distance contracts;
2. exact vector Top-K under cosine, dot-product, and Euclidean metrics;
3. deterministic HNSW construction and approximate search;
4. JSON payload filtering with optional field indexes;
5. why filter cardinality changes the best vector-search strategy;
6. how payload indexes and vector indexes cooperate rather than replace one
   another;
7. appendable versus optimized immutable segments;
8. global point versioning, tombstones, and duplicate point IDs across
   segments;
9. WAL-before-apply mutation durability and ordered replay;
10. online segment rebuild while old segments remain readable;
11. atomic manifest publication and obsolete-segment reclamation;
12. scalar quantization, candidate oversampling, exact rescoring, and recall
    trade-offs;
13. snapshot, crash recovery, and deterministic failure experiments.

## 4. Non-goals

MiniQdrant does not implement:

- Qdrant REST, gRPC, client, or storage-format compatibility;
- a remote server, authentication, TLS, quotas, or multi-tenancy;
- sparse vectors, named vectors, multivectors, recommendation queries, fusion,
  grouping, discovery, sampling, or full-text search;
- geographic, datetime, UUID-specialized, or text payload indexes;
- sharding, replication, Raft, consensus, membership, election, or failover;
- distributed consistency or write-ordering modes;
- production-grade filterable-HNSW payload edge augmentation or ACORN;
- mmap vector storage, RocksDB/Gridstore, GPU, SIMD, or native extensions;
- binary or product quantization;
- automatic resource tuning or a production background optimizer;
- online schema migration;
- application RAG pipelines or embedding generation;
- course chapters, day files, learner quizzes, or instructional scaffolding.

## 5. Architecture

```text
Direct Client / thin CLI
          │
          ▼
      Database
          │ collection name
          ▼
      Collection
  ┌───────┼───────────┬──────────────┐
  ▼       ▼           ▼              ▼
Updater  Searcher   Optimizer     Snapshotter
  │       │           │              │
  ▼       ▼           ▼              ▼
 WAL   QueryPlanner  SegmentBuilder  Manifest root
  │       │           │
  └──→ SegmentSet ←───┘
       ├── appendable plain segment
       └── immutable optimized segments
             ├── vector storage
             ├── HNSW index
             ├── payload storage/indexes
             ├── point versions
             └── tombstones
```

### 5.1 Ownership

- `Database` owns collection creation, open, close, drop, and directory names.
- `Collection` is the sole semantic owner of ordered updates, segment-set
  publication, search snapshots, optimizer scheduling, and shutdown.
- `Wal` owns monotonically increasing operation sequence numbers and durable
  mutation frames.
- `MutableSegment` owns the current appendable point versions and plain vector
  index.
- `ImmutableSegment` owns checksummed files and immutable vector/payload
  indexes. Deletes are represented by a versioned overlay.
- `QueryPlanner` selects one search strategy independently for each segment.
- `SegmentOptimizer` builds replacement segments outside the collection write
  lock and publishes them with one manifest transition.
- `Snapshotter` captures a committed manifest root and the required WAL
  boundary.
- Adapters validate and translate. They do not mutate segments directly or own
  query semantics.

### 5.2 Concurrency

Updates are serialized per collection. Search acquires an immutable
`CollectionView`, increments segment references, and then releases the
collection lock before doing distance work.

Optimization follows:

```text
capture immutable source view at version V
→ build replacement outside lock
→ reacquire publication lock
→ retain later versions from the appendable segment
→ atomically publish new manifest
→ retire old segments after readers release them
```

No lock is held while calling user code. Search never observes half-published
segments or a manifest referencing missing files.

## 6. Domain model

### 6.1 Collection schema

```python
CollectionConfig(
    dimension: int,
    distance: Distance,
    hnsw: HnswConfig,
    optimizer: OptimizerConfig,
    quantization: ScalarQuantizationConfig | None = None,
)
```

`dimension` is positive and immutable. `Distance` is `COSINE`, `DOT`, or
`EUCLID`. All vector components must be finite floats.

Cosine vectors are normalized exactly once at mutation validation. A zero-norm
cosine vector is rejected. Public search scores always sort higher-is-better:

```text
cosine  = normalized dot product
dot     = dot product
euclid  = negative squared L2 distance
```

Equal scores use canonical point-ID ordering as a deterministic tie-breaker.

### 6.2 Points

```python
Point(
    id: int | UUID,
    vector: tuple[float, ...],
    payload: JsonObject,
)
```

Integer IDs are unsigned 64-bit values. UUID inputs are canonicalized.
Payloads are immutable JSON-compatible values after validation. NaN, infinity,
custom Python objects, and non-string object keys are rejected.

Supported mutations are:

- batch upsert;
- delete points by ID;
- replace payload;
- merge payload fields;
- delete payload keys.

Every mutation is all-or-nothing at the batch boundary. Complete validation
happens before WAL append.

### 6.3 Versions and tombstones

The WAL sequence number is the operation version. Every point image and delete
tombstone carries a version.

The same external point ID may temporarily exist in multiple segments.
Retrieval and search resolve the greatest version before returning results.
A tombstone with the greatest version hides all older images.

An operation with a version not greater than the version already known for the
point is idempotently ignored during replay. This prevents stale WAL records or
optimizer output from resurrecting old data.

## 7. Payload filters and indexes

The filter AST is:

```text
Filter(must, should, must_not)
├── Match(field_path, scalar)
├── Range(field_path, gt/gte/lt/lte)
├── HasId(ids)
└── nested Filter
```

`must` is conjunction, `must_not` excludes matches, and `should` requires at
least one match when non-empty. Field paths use dot notation through JSON
objects. Arrays have any-element semantics for scalar match and range
conditions.

Payload index schemas are explicit:

- `KEYWORD` for strings;
- `INTEGER`;
- `FLOAT`;
- `BOOL`.

An index is created at collection level and materialized independently in each
optimized segment. The appendable segment maintains a small in-memory index so
new writes become immediately searchable.

An index provides:

```python
CardinalityEstimate(
    minimum: int,
    expected: int,
    maximum: int,
    exact: bool,
)
```

It may also produce a candidate-ID set. Unindexed conditions remain valid and
fall back to payload evaluation; they never silently change query results.

## 8. Vector indexes

### 8.1 Exact index

`PlainVectorIndex` scans live candidates, computes exact scores, and maintains
a bounded Top-K heap. It is the correctness oracle for every approximate
search test.

### 8.2 HNSW

The pure-Python HNSW implementation supports:

- deterministic seeded level generation;
- bounded degree `m`;
- construction breadth `ef_construct`;
- search breadth `ef_search`;
- greedy descent on upper levels;
- best-first expansion on level zero;
- soft deletion;
- immutable graph serialization and validation.

`ef_search` is raised to at least `limit`. HNSW returns approximate candidates;
it never claims exact ordering.

Filtered HNSW traverses the complete live graph but admits only matching
points to the result heap. This preserves reachability better than pruning
nonmatching traversal nodes, but it does not implement Qdrant's production
payload-specific supplemental graph edges. That difference is documented and
demonstrated with a recall experiment.

### 8.3 Scalar quantization

Optional scalar quantization maps each dimension to signed 8-bit values using
per-dimension min/max calibration stored in the segment.

The original float vector remains available. Quantized search:

```text
quantized HNSW candidate generation
→ oversample limit × factor
→ exact float rescoring
→ final Top-K
```

The repository reports compression ratio, candidate recall, and final recall.
Quantization is never used as the only durable representation.

## 9. Query planning and execution

Planning is per segment. The closed strategy set is:

1. `EXACT_FULL_SCAN`: explicitly exact or segment below the plain threshold;
2. `FILTER_THEN_EXACT`: indexed filter estimate is small enough to enumerate;
3. `HNSW`: large unfiltered approximate search;
4. `FILTERED_HNSW`: large filtered candidate population;
5. `QUANTIZED_HNSW_RESCORE`: quantization enabled and exact mode is false.

The planner emits an inspectable `SearchPlan` containing estimates, thresholds,
chosen strategy, and reason. Tests assert result parity where the strategy is
exact and measure recall where it is approximate.

Each segment produces more than `limit` candidates when cross-segment
deduplication may remove stale versions. The collection searcher resolves
versions/tombstones, applies any residual filter, recomputes exact scores when
required, and performs a final bounded Top-K merge.

Search supports:

```python
SearchRequest(
    vector,
    limit,
    filter=None,
    score_threshold=None,
    exact=False,
    ef_search=None,
    with_payload=True,
    with_vector=False,
)
```

`limit` is positive and bounded by configuration. Searches run against one
captured collection view and therefore have point-in-time segment visibility.

## 10. Segment lifecycle

### 10.1 Files

```text
collections/products/
├── collection.json
├── manifest-00000000000000000007.json
├── CURRENT
├── wal/
│   └── 00000000000000000001.wal
├── segments/
│   └── seg-<uuid>/
│       ├── meta.json
│       ├── points.bin
│       ├── payloads.bin
│       ├── versions.bin
│       ├── deleted.bin
│       ├── hnsw.bin
│       ├── payload-indexes.bin
│       └── quantized.bin
└── snapshots/
```

All formats are custom, length-delimited, versioned, and checksummed. JSON is
used only for small human-readable metadata. Python `pickle` is forbidden.

### 10.2 Flush

When the appendable segment reaches a configured point or byte threshold:

1. freeze its view;
2. create a new empty appendable segment;
3. write the frozen plain segment to a temporary directory;
4. fsync files and directory;
5. atomically publish a new manifest;
6. advance the replay boundary;
7. truncate obsolete WAL only after publication is durable.

### 10.3 Optimization

The optimizer exposes explicit deterministic methods and an optional bounded
background runner:

- indexing optimizer: rebuild a large plain segment with HNSW and indexes;
- merge optimizer: combine the smallest eligible segments;
- vacuum optimizer: rebuild a segment whose deleted ratio crosses a threshold;
- quantization optimizer: add or rebuild scalar quantization.

Old segments remain readable during a rebuild. Publication either exposes the
complete replacement or leaves the previous set intact. Temporary,
unreferenced build directories are removed during startup recovery.

## 11. WAL, commit, recovery, and snapshots

### 11.1 WAL

Each WAL frame contains:

```text
magic
format version
frame length
operation sequence
operation kind
stable payload
CRC32
```

Mutation order is:

```text
validate complete batch
→ append WAL frame
→ fsync according to durability policy
→ apply sequentially to mutable state
→ return operation result
```

Durability policies are `always`, `interval`, and `manual`. Only `always`
promises that an acknowledged update survives process loss. Interval and
manual modes expose their loss window in tests and documentation.

An incomplete or corrupt active WAL tail is truncated to the last valid frame.
Corruption before the active tail is a startup error.

### 11.2 Manifest

The manifest names the complete active segment set, per-segment generation,
collection schema fingerprint, and replay boundary. It is written to a
temporary file, fsynced, renamed, and selected through an atomically replaced
`CURRENT` pointer.

Startup:

1. validates collection config and `CURRENT`;
2. loads and checks every referenced segment;
3. reconstructs the latest point-version map;
4. replays WAL operations newer than the manifest boundary;
5. removes unreferenced temporary builds;
6. opens one appendable segment.

Missing or corrupt referenced immutable files are fatal. Recovery never
silently drops a published segment.

### 11.3 Snapshots

A snapshot captures:

- collection config;
- one committed manifest;
- every segment referenced by it;
- WAL records required after its replay boundary;
- checksums and snapshot metadata.

Snapshot creation uses a temporary directory and atomic rename. Restore
validates all checksums before replacing any live collection directory.
Failure leaves the old collection intact.

## 12. Public API

```python
db = Database.open("./data")

products = db.create_collection(
    "products",
    dimension=4,
    distance=Distance.COSINE,
)

products.create_payload_index("category", PayloadSchema.KEYWORD)
products.create_payload_index("price", PayloadSchema.FLOAT)

products.upsert(
    [
        Point(1, (0.9, 0.1, 0.0, 0.0), {"category": "book", "price": 12.0}),
        Point(2, (0.8, 0.2, 0.1, 0.0), {"category": "book", "price": 30.0}),
    ]
)

result = products.search(
    SearchRequest(
        vector=(1.0, 0.0, 0.0, 0.0),
        limit=10,
        filter=Filter(
            must=(
                Match("category", "book"),
                Range("price", lte=20.0),
            )
        ),
    )
)

products.optimize()
snapshot = products.create_snapshot("./backups/products-001")
db.close()
```

The CLI is a thin local adapter:

```text
miniqdrant create DATA COLLECTION --dimension N --distance cosine
miniqdrant upsert DATA COLLECTION POINTS_JSONL
miniqdrant search DATA COLLECTION VECTOR_JSON [options]
miniqdrant payload-index DATA COLLECTION FIELD TYPE
miniqdrant optimize DATA COLLECTION
miniqdrant snapshot DATA COLLECTION TARGET
miniqdrant info DATA COLLECTION
```

## 13. Error and lifecycle contract

Public exceptions are typed:

- `CollectionExistsError`;
- `CollectionNotFoundError`;
- `SchemaMismatchError`;
- `InvalidPointError`;
- `InvalidVectorError`;
- `InvalidFilterError`;
- `PayloadIndexError`;
- `CorruptionError`;
- `ClosedResourceError`;
- `SnapshotError`.

Validation errors occur before durable mutation. A failure after WAL fsync but
before apply has an ambiguous immediate outcome but is resolved by replay on
restart. Repeating the same operation version is idempotent internally.

`close()` is idempotent. It stops the optional optimizer, flushes according to
policy, closes files, waits for owned readers, and rejects new work. No
background failure is swallowed; it is surfaced on the next public call and
during close.

## 14. Required invariants

```text
collection dimension and metric never change after creation
all stored vector components are finite
cosine vectors are normalized exactly once
point version increases monotonically per external ID
the greatest visible version wins across all segments
a greatest-version tombstone prevents resurrection
one segment never contains two live images of the same external ID
payload index results equal residual payload evaluation
exact search equals brute-force reference ordering
HNSW never returns a deleted or filter-rejected point
search uses one immutable collection view
manifest publication is all-or-nothing
WAL sequence numbers are unique and strictly increasing
manifest replay boundary never exceeds durably represented operations
WAL replay is idempotent
optimizer output cannot overwrite a later point version
obsolete segments are deleted only after all readers release them
snapshot restore validates before replacing live state
quantized search retains original vectors for exact rescoring
```

## 15. Testing and experiments

Tests are deterministic and grouped by evidence:

- unit: metrics, normalization, filters, indexes, heaps, codecs;
- property: exact Top-K versus a simple reference implementation;
- HNSW: graph invariants, deterministic build, recall curves over `ef_search`;
- planning: strategy boundaries and identical exact results across plans;
- segment: version resolution, deletes, flush, merge, vacuum;
- reliability: corrupt tails, manifest interruption, restart replay;
- concurrency: readers during optimize, late writes, safe reclamation;
- snapshot: complete restore and injected failure before publication;
- quantization: compression, candidate recall, rescore recall;
- acceptance: cross-update, cross-segment, cross-restart, and cross-optimizer
  scenarios.

Required labs:

```text
exact scan vs HNSW latency/recall
ef_search vs recall and visited nodes
unindexed filter vs payload-index candidate reduction
planner strategy as filter selectivity changes
many small segments vs merged segment search work
delete accumulation vs vacuum rebuild
crash after WAL fsync before apply
reader continuity during online optimization
int8 quantization before and after exact rescore
```

The test suite uses injected clocks, deterministic random seeds, explicit
failure gates, and bounded data sets. Wall-clock performance is reported but
never asserted as a correctness gate.

## 16. Delivery phases

The project is implemented as one finished reference repository:

1. foundation and exact retrieval;
2. payload filters, indexes, and inspectable query planner;
3. deterministic HNSW and approximate-search experiments;
4. WAL, mutable segments, immutable codecs, manifest, and restart;
5. online indexing, merge, vacuum, and safe reader snapshots;
6. scalar quantization and exact rescoring;
7. snapshots, CLI, lifecycle hardening, documentation, and final acceptance.

These phases are implementation units, not course chapters.

## 17. Acceptance

The project is complete only when:

- all required capabilities and invariants have direct tests;
- exact and approximate paths are separately labeled and verified;
- every durability claim names its acknowledgement boundary;
- online optimization is proven not to hide later writes;
- snapshot and restart behavior survive injected failures;
- the public API and CLI execute documented examples;
- README, architecture notes, format docs, behavior matrix, and labs match the
  implementation;
- formatting, static checks, compilation, the full test suite, and
  `git diff --check` pass from a clean checkout;
- the git worktree is clean and the completed implementation is committed.

