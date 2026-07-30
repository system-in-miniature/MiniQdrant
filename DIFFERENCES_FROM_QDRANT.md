> **Language**: English | [简体中文](docs/zh/DIFFERENCES_FROM_QDRANT.md)

# Differences from Qdrant

MiniQdrant preserves selected single-node invariants while deliberately
omitting product compatibility. Names shared with Qdrant describe the teaching
topic, not identical implementation or performance.

For the positive correspondence between modules, see
[`docs/qdrant-mapping.md`](docs/qdrant-mapping.md).

## Product scope

| Area | MiniQdrant | Qdrant |
|---|---|---|
| Access | Python API and thin local CLI | REST, gRPC, official clients |
| Vectors | one dense vector per point | dense, sparse, named, multi-vector |
| Payload indexes | keyword, integer, float, bool | broader production index set |
| Retrieval | exact, deterministic HNSW, scalar quantization | production HNSW/filtering/quantization stack |
| Storage | custom teaching WAL/segment/manifest | Qdrant formats and storage engines |
| Deployment | one process, one writer per collection | shards, replicas, distributed coordination |
| Optimizer | explicit deterministic full rebuild | adaptive background optimizers |
| Snapshot | collection root, custom checksum format | Qdrant snapshot compatibility |

Not implemented: Qdrant wire/storage compatibility, sparse or hybrid search,
recommendation/fusion/grouping, scroll and batch search, geo/text/datetime
indexes, mmap/RocksDB, sharding, replication, Raft, authentication, TLS,
quotas, multi-tenancy, GPU, SIMD/native kernels, and online schema migration.

## Declared semantic and performance differences

1. **Filtered HNSW is post-filtering plus fixed oversampling.**
   `HnswIndex.search()` traverses the graph without consulting `allowed_ids`;
   membership is checked only while collecting candidates, and the segment asks
   for up to `limit * 4` candidates. This is exactly the post-filtering pattern
   Qdrant's filter-aware HNSW design criticizes: selective filters can discard
   the nearest candidates after traversal, returning fewer hits or worse recall,
   while increasing oversampling wastes work without guaranteeing enough
   matches. Qdrant incorporates filter constraints into graph traversal (with
   additional strategies for difficult filters).

2. **The scalar-quantized path is a decoded-float full scan, not an HNSW
   scorer.** MiniQdrant scans every eligible quantized code, decodes both the
   quantized query and stored codes back to float vectors, scores those floats,
   oversamples, and exactly rescores the survivors. Real Qdrant can use an int8
   quantized scorer during HNSW traversal and rescore selected candidates.
   MiniQdrant therefore teaches the two-stage approximation/rescore shape, but
   neither integer scoring nor the production asymptotic benefit.

3. **Every collection search has an O(N) view-capture cost.**
   `capture_view()` rebuilds `_latest_records` by scanning all immutable and
   mutable records, and rebuilds the mutable snapshot (including payload
   indexes). `_stale_live_count()` then scans each searched segment again.
   Consequently, even when per-segment HNSW visits few nodes, end-to-end search
   remains linear in the collection size. Qdrant maintains incremental ID and
   segment tracking instead of reconstructing global visibility per query.

4. **Duplicate IDs inside one upsert batch are first-wins.** Every item in the
   batch receives the same WAL sequence/version, and `MutableSegment` rejects a
   same-version replacement. Qdrant batch/update behavior is last-write-wins for
   repeated point IDs. Callers must deduplicate a MiniQdrant batch themselves if
   they want Qdrant-like behavior.

5. **Payload field paths automatically expand arrays.** MiniQdrant's path
   walker descends through list elements without an explicit marker. Qdrant
   uses explicit `[]` path notation and has distinct nested-array matching
   semantics, including element-local nested conditions. A filter copied
   between the systems can therefore match a different set of points.

6. **Euclidean scores are negative squared distances.** All MiniQdrant metrics
   use one higher-is-better internal convention, so Euclidean exposes
   `-(distance²)`. `score_threshold` is always applied as `score >= threshold`;
   Euclidean callers must pass a negative squared-distance threshold. Qdrant's
   API interprets threshold direction according to the selected metric, so
   numeric thresholds are not portable.

7. **`QUANTIZED_HNSW_RESCORE` is a misleading strategy name.** Selecting this
   plan bypasses `_hnsw` entirely and invokes `ScalarQuantizedIndex`'s full
   scan. The result's `plan` is useful for observing the branch, but it is not
   evidence that HNSW ran.

8. **Persisted `hnsw.bin` is validated and then discarded.**
   `SegmentCodec.read()` decodes the graph into `SegmentImage.hnsw_graph`, but
   `SegmentImage.to_segment()` passes only `indexed=True`; constructing the
   immutable segment rebuilds HNSW from all live points. Unlike Qdrant's
   reusable persisted index, this makes open/restart pay graph-construction cost
   and turns `hnsw.bin` into write-only semantic data.

9. **HNSW search can restart exhaustively across disconnected components.**
   When the first layer-0 search produces fewer than `breadth` scores,
   MiniQdrant repeatedly starts at the smallest unvisited point ID. This is not
   standard HNSW behavior. On fragmented graphs or large `ef_search`, it can
   visit every vector, hiding poor graph connectivity in recall tests and
   degenerating approximate search into a full scan.

10. **Optimizer policy and automatic flush thresholds are not connected to the
    runtime.** `choose_optimization()` and `flush_threshold_points` are used by
    tests/configuration only. Upserts do not trigger flush or background work,
    and explicit `merge()`, `vacuum()`, and `optimize()` all rewrite the full
    captured segment set. The planner also reuses
    `indexing_threshold_points` for both plain-scan and filter-scan decisions,
    whereas Qdrant exposes a distinct full-scan threshold.

11. **The WAL never truncates, rotates, or reclaims published history.** Flush
    and optimization advance `replay_boundary`, so covered frames are skipped
    during recovery, but the single
    `00000000000000000001.wal` file grows forever. Its numbered filename does
    not imply implemented multi-file rotation. Qdrant reclaims WAL history that
    is safely covered by persisted state.

## Other deliberate simplifications

The HNSW implementation uses deterministic levels, tie-breaking, and a
nearest-only pruning rule for inspectability rather than production recall and
throughput. Segment `.bin` files contain framed JSON rather than native binary
or mmap layouts. Non-exact payload cardinality estimates use a fixed teaching
heuristic. `SearchRequest.filter` is typed as `object | None` and checked at
runtime rather than exposing a fully self-documenting client schema.

Durability policies expose local crash boundaries, not a distributed
write-consistency contract. Payload field merge/delete is intentionally
shallow; nested patch languages and Qdrant API compatibility are outside scope.
