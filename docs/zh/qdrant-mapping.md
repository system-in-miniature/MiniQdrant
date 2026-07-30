> **Language**: [English](../qdrant-mapping.md) | 简体中文

# MiniQdrant ↔ Qdrant 映射

本指南将 MiniQdrant 的教学边界映射到真实 Qdrant 中最接近的概念。它是一份概念性阅读地图，并不声称具有 API 或源代码级兼容性。

## 如何理解标签

- **等价（equivalent）**：尽管格式更小或运行模式更少，但教授的是相同的核心不变量。
- **有意简化（deliberately simplified）**：组件承担相同的架构角色，但去除了规模、并发、存储引擎或 API 机制。
- **语义相反（semantically opposite）**：名称或位置让人联想到 Qdrant 机制，但重要的运行时行为却走向相反方向。

## 运行时与存储

| MiniQdrant module or symbol | Closest Qdrant subsystem | Label | What carries over, and what does not |
|---|---|---|---|
| `database.py::Database` | collection catalogue and collection lifecycle | deliberately simplified | Owns named collection directories and open/close, but has no distributed collection metadata, shards, replicas, aliases, or consensus. |
| `collection.py::Collection` | collection/shard update and search orchestration | deliberately simplified | Orders writes, captures read views, resolves versions, and publishes segment sets in one process. Qdrant distributes these responsibilities across collection, shard, replica-set, and update/search services. |
| `CollectionView` | stable segment read guard / snapshot of a shard's searchable segments | equivalent | Searches retain the exact immutable segment set they captured, so replacement cannot invalidate an in-flight read. |
| `segment/references.py::SegmentHandle` | `SegmentHolder` ownership plus the lifetime role of proxy segments | deliberately simplified | Reference counting delays deletion of retired paths. Qdrant's holder manages a segment set and proxy segments also mediate concurrent updates during optimization; one MiniQdrant handle does not implement that full abstraction. |
| `segment/mutable.py::MutableSegment` | appendable segment | deliberately simplified | Accepts newest versions and tombstones in memory, without Qdrant's RocksDB/mmap-backed storage and richer vector/payload indexes. |
| `segment/immutable.py::ImmutableSegment` | immutable/plain/indexed segment | deliberately simplified | Co-locates records, payload indexes, HNSW, and quantization for per-segment search, but loads everything into Python objects. |
| `_latest_records` and greatest-version checks | segment `id_tracker` plus point-version visibility | deliberately simplified | Enforces newest-version visibility, but rebuilds an external-ID map by scanning all records for each view instead of maintaining an incremental tracker. |
| `segment/codec.py` column files | segment persistence and segment component files | deliberately simplified | Separates vectors, payloads, versions, tombstones, graph, and payload-index metadata. The `.bin` contents are framed JSON, not Qdrant's native/mmap formats. |
| `SegmentImage.hnsw_graph` / `hnsw.bin` load path | persisted HNSW graph | semantically opposite | MiniQdrant writes and validates the graph but `to_segment()` discards it and rebuilds HNSW. Qdrant persists indexes so opening a segment reuses them. |
| `persistence/frame.py` + `wal.py` | collection/shard WAL | equivalent | WAL-before-apply, monotonic sequence numbers, framed checksums, fsync policy, replay, and torn-tail handling preserve the core durability lesson. It remains one unbounded file. |
| `Manifest` + `ManifestStore` + `CURRENT` | segment inventory / shard state manifest and atomic publication | equivalent | A checksummed immutable generation is fsynced before one root pointer commits it; the format and ownership are MiniQdrant-specific. |
| `replay_boundary` | WAL recovery checkpoint covered by persisted segment state | equivalent | Replay applies only later operations, making recovery idempotent. It does not cause WAL truncation. |
| `persistence/snapshot.py` | collection/shard snapshots | deliberately simplified | Checksums, staging, fsync, atomic rename, validate-before-replace, and rollback are preserved; Qdrant snapshots also participate in distributed shard/replica workflows and use different formats. |

## 查询与索引

| MiniQdrant module or symbol | Closest Qdrant subsystem | Label | What carries over, and what does not |
|---|---|---|---|
| `filters/ast.py` + `evaluate.py` | payload filter condition tree | deliberately simplified | `must`/`should`/`must_not`, match, range, and ID conditions are recognizable. Field paths automatically traverse arrays instead of using Qdrant's explicit array-path/nested semantics. |
| `filters/index.py` | structured payload indexes | deliberately simplified | Keyword, integer, float, and bool indexes supply candidates plus residual evaluation, without Qdrant's broader index set and storage backends. |
| `filters/cardinality.py` | payload-index cardinality estimation | deliberately simplified | Feeds lower/expected/upper estimates to planning. Non-exact expected values use a teaching heuristic rather than production statistics. |
| `query/planner.py::QueryPlanner` | cardinality-based filter/search strategy selection | deliberately simplified | Chooses scan versus graph per segment from cardinality and index presence. One threshold is reused for plain and filtered scans, while Qdrant has a distinct full-scan threshold and more inputs. |
| `index/plain.py` | plain vector index / exact scorer | equivalent | Exhaustively scores eligible vectors and returns deterministic Top-K. Python loops replace native SIMD scoring. |
| `index/hnsw.py::HnswIndex` | HNSW vector index | deliberately simplified | Retains deterministic levels, an entry point, greedy upper-layer descent, ef breadth, and bounded degree. Nearest-only pruning and exhaustive component restarts differ from production HNSW. |
| `Strategy.FILTERED_HNSW` | Qdrant filter-aware HNSW traversal | semantically opposite | MiniQdrant traverses without filter awareness, oversamples, then filters candidates. Qdrant integrates filtering with graph traversal specifically to avoid post-filter recall and latency failures. |
| `index/quantization.py::ScalarQuantizedIndex` | scalar quantization scorer used with HNSW | semantically opposite | MiniQdrant scans every eligible code, decodes codes back to floats for approximate scoring, and bypasses HNSW. Qdrant can use an int8 scorer during HNSW traversal and then rescore selected candidates. |
| `query/executor.py::execute_quantized_rescore` | approximate candidate selection plus exact rescore | deliberately simplified | The two-stage candidate/rescore shape matches; the candidate source and arithmetic do not. |
| `topk.py::TopK` | bounded scored-point collection and cross-segment result merge | equivalent | Maintains higher-is-better ordering with deterministic ID tie-breaking; the implementation is single-process and in Python. |
| `metrics.py` | metric-specific raw scorers | deliberately simplified | Cosine, dot, and Euclidean ranking exist. Euclidean is exposed as negative squared distance, which changes user-facing threshold interpretation. |

## 优化与教学表面

| MiniQdrant module or symbol | Closest Qdrant subsystem | Label | What carries over, and what does not |
|---|---|---|---|
| `optimizer/optimizer.py::build_replacement` | merge, vacuum, and indexing optimizers | deliberately simplified | Rewrites versions into a compact indexed segment and can drop tombstones. It always operates as part of a full explicit rewrite. |
| `optimizer/policy.py::choose_optimization` | optimizer condition/policy selection | semantically opposite | The module looks like runtime scheduling policy but is test-only dead code; `Collection` never calls it and never auto-flushes from `flush_threshold_points`. |
| `Collection._optimize` late-write preservation | proxy-segment/concurrent optimization reconciliation | deliberately simplified | Builds outside the update lock, then keeps records newer than the captured WAL boundary. Qdrant uses richer proxy/change-tracking machinery. |
| `config.py` | collection, HNSW, optimizer, quantization configuration | deliberately simplified | Exposes the knobs needed by the teaching mechanisms, without Qdrant's full configuration schema or compatibility rules. |
| `models.py` + `cli.py` | public point/search models and REST/gRPC/client surface | deliberately simplified | Provides a typed local Python API and thin CLI, not Qdrant wire compatibility. |
| `labs/` and `SearchResult.plan` | telemetry, explainability, benchmarks, and integration tests | deliberately simplified | Makes strategy selection and visited work visible for experiments. It is deterministic teaching instrumentation, not Qdrant telemetry compatibility. |

## 建议阅读顺序

1. 从 `collection.py` 开始，了解写入、视图、可见性和发布边界。
2. 结合 `query/planner.py` 阅读 `segment/immutable.py`，了解按分段选择计划的过程。
3. 比较 `index/plain.py`、`index/hnsw.py` 和 `index/quantization.py`。
4. 沿 `wal.py` → `frame.py` → `manifest.py` 理解崩溃恢复。
5. 最后阅读 `optimizer/optimizer.py`、`_optimize` 和 `segment/references.py`，了解在线替换和延迟删除。

有关行为后果而不是组件对应关系，请参阅 [`DIFFERENCES_FROM_QDRANT.md`](DIFFERENCES_FROM_QDRANT.md)。
