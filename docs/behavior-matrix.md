# Behavior and evidence matrix

Every retained project claim below names its implementation boundary, direct
evidence, failure/quality experiment where applicable, and deliberate
difference from Qdrant.

## Product goals

| Goal | Public API / module | Direct test | Failure or quality evidence | Scoped difference |
|---|---|---|---|---|
| Fixed collection schema | `Database.create_collection`, `CollectionConfig` | `tests/unit/test_domain.py`, `tests/contract/test_collection.py` | reopen schema fingerprint check | one dense vector schema only |
| Exact deterministic Top-K | `Collection.search(exact=True)`, `PlainVectorIndex`, `TopK` | `tests/unit/test_metrics.py`, `test_topk.py`, `tests/acceptance/test_exact_collection.py` | brute-force and tie-order fixtures | Python reference arithmetic, no SIMD |
| Deterministic HNSW | `HnswIndex`, `ImmutableSegment.search` | `tests/index/test_hnsw_graph.py`, `test_hnsw_search.py` | `test_hnsw_recall.py`, deterministic recall lab | teaching graph, not Qdrant HNSW/ACORN |
| JSON payload filters | `Filter`, `Match`, `Range`, `HasId` | `tests/contract/test_filters.py` | indexed/unindexed parity | no text, geo, datetime, or nested-object index |
| Cardinality planning | `QueryPlanner`, `PayloadIndexSet` | `tests/query/test_planner.py`, `test_payload_index.py` | `test_plan_parity.py` | fixed inspectable thresholds |
| Payload mutation | `replace_payload`, `merge_payload`, `delete_payload_keys` | `tests/contract/test_collection.py` | close/reopen replay in same test | full point images in WAL, shallow top-level field edits |
| Mutable/immutable lifecycle | `MutableSegment`, `ImmutableSegment`, `flush` | `tests/contract/test_mutable_segment.py`, `tests/storage/test_segment_codec.py` | cross-segment acceptance | in-memory active segment; custom immutable format |
| Versions and tombstones | WAL sequence, `StoredPoint.version` | `tests/acceptance/test_cross_segment_search.py` | many-stale-candidates regression; delete overlay | one process assigns versions |
| WAL-before-apply recovery | `Wal`, `Collection.upsert/delete` | `tests/storage/test_wal_codec.py`, `tests/reliability/test_wal_replay.py` | corrupt-tail and crash-boundary injection | one WAL file; interval policy is not a production flusher |
| Online optimization | `optimize`, `merge`, `vacuum`, `OptimizationGate` | `tests/storage/test_merge.py`, `test_vacuum.py` | late-write, old-reader, failed-publish tests | explicit full rewrite; policy is a pure deterministic teaching component |
| Safe reclamation | `CollectionView`, `SegmentHandle` | `tests/concurrency/test_online_optimize.py` | old path exists until view release | process-local reference counting |
| Scalar quantization | `ScalarQuantizer`, `ScalarQuantizedIndex` | `tests/index/test_quantization.py` | exact-rescore and ≥0.95 recall floor | scans encoded candidates; codes rebuilt on open |
| Snapshot and restore | `create_snapshot`, `Database.restore_collection` | `tests/acceptance/test_snapshot_roundtrip.py` | checksum corruption, create failure, restore rollback | custom collection snapshot; target DB must not have another writer |
| Thin adapters and labs | `miniqdrant` CLI, `miniqdrant.labs` | `tests/acceptance/test_cli.py`, `test_labs.py` | fixed seeds and bounded fixtures | no REST/gRPC server |

## Required invariants

| Invariant | Enforcement | Evidence |
|---|---|---|
| dimension/metric never change | frozen config plus persisted fingerprint | domain and restart tests |
| vector components are finite | `validate_vector` before WAL append | `tests/unit/test_domain.py` |
| cosine is normalized once | validation stores normalized vector | metric/domain tests |
| versions strictly increase | contiguous WAL sequence is mutation version | WAL codec/replay tests |
| greatest visible version wins | view-wide `_latest_records` | cross-segment tests |
| greatest tombstone prevents resurrection | candidate version rejection | delete-overlay and vacuum tests |
| one segment has one highest image per ID | immutable `_highest_versions`; mutable version guard | mutable/segment codec tests |
| indexed candidates equal residual evaluation | candidate set plus residual filter | filter and plan-parity tests |
| exact ordering equals brute force | plain score plus bounded Top-K | exact collection/metric tests |
| HNSW excludes deleted/filter-rejected output | payload candidate admission and live records | HNSW plan/search tests |
| one search uses one stable view | `capture_view` snapshots handles and mutable records | online optimizer reader test |
| publication is all-or-nothing | temp files, fsync, `CURRENT` replace | manifest and optimizer publish injection |
| WAL sequence is unique/ordered | frame scan validates contiguous sequence | WAL codec/tail tests |
| replay boundary is represented | flush/optimizer publish segment before manifest | crash-boundary and restart tests |
| replay is idempotent | segment/mutable greatest-version guards | WAL replay and cross-restart tests |
| optimizer cannot overwrite later write | post-boundary mutable rebuild | gated late-write test |
| obsolete path waits for readers | `SegmentHandle` references | existing-view merge test |
| restore validates before replacement | checksums, staged `Collection.open`, rollback | snapshot restore failure tests |
| quantized result uses original floats | oversample then `score(... original vector)` | quantized rescore test |
| shutdown waits owned work | optimizer lock and active-view condition | lifecycle concurrency tests |
| persisted segment IDs cannot escape root | manifest ID format and uniqueness validation | manifest traversal tests |

## Claim boundary

“Atomic” refers to a single-filesystem rename/publication boundary tested with
named failure injection; it is not a distributed transaction. “Durable” refers
to the selected local WAL policy and documented fsync points. MiniQdrant makes
no claim of production suitability, Qdrant compatibility, multi-process writer
safety, replication, consensus, or zero data loss under hardware/filesystem
failure.
