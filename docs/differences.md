# Differences from Qdrant

The canonical, detailed list is maintained at the repository root:
[read the full differences document](https://github.com/system-in-miniature/MiniQdrant/blob/main/DIFFERENCES_FROM_QDRANT.md).

MiniQdrant preserves selected single-node invariants but deliberately omits
product compatibility. Its Python API, custom WAL/segments, explicit optimizer,
and collection snapshots are teaching surfaces, not Qdrant-compatible formats
or endpoints.

Important boundaries include:

- filtered HNSW uses post-filtering with fixed oversampling;
- the scalar-quantized branch performs decoded-float scanning and exact
  rescoring rather than an integer HNSW scorer;
- view capture is O(N), even when the selected per-segment plan is approximate;
- duplicate IDs in one upsert batch are first-wins;
- Euclidean scores use negative squared distance;
- persisted HNSW data is validated but the graph is rebuilt at open;
- optimizer policy and automatic flush thresholds are not runtime automation;
- WAL history is not rotated or reclaimed.

These choices make mechanisms observable, but their plan names and data files
must not be treated as evidence of Qdrant compatibility or performance. Use the
[Qdrant mapping](qdrant-mapping.md) for positive correspondence and the
[behavior matrix](behavior-matrix.md) for executable evidence.
