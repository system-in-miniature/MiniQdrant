# Differences from Qdrant

MiniQdrant preserves selected single-node semantics while deliberately omitting
product compatibility.

| Area | MiniQdrant | Qdrant |
|---|---|---|
| Access | Python API and thin local CLI | REST, gRPC, clients |
| Vectors | one dense vector per point | dense, sparse, named, multi-vector |
| Payload indexes | keyword, integer, float, bool | broader production index set |
| Retrieval | exact, deterministic HNSW, scalar quantization | production HNSW/filtering/quantization stack |
| Storage | custom teaching WAL/segment/manifest | Qdrant formats and storage engines |
| Deployment | one process, one writer per collection | shards, replicas, distributed coordination |
| Optimizer | explicit deterministic rebuild | adaptive production optimizers |
| Snapshot | collection root, custom checksum format | Qdrant snapshot compatibility |

Not implemented: Qdrant wire/storage compatibility, sparse or hybrid search,
recommendation/fusion/grouping, geo/text/datetime indexes, mmap/RocksDB,
sharding, replication, Raft, authentication, TLS, quotas, multi-tenancy, GPU,
SIMD/native kernels, and online schema migration.

The HNSW implementation favors determinism and inspectability over throughput.
Scalar quantization scans encoded vectors to choose an oversampled candidate
set; it is not a compressed production SIMD index. Durability policies expose
teaching boundaries, not a distributed write-consistency contract.
Payload field merge/delete is intentionally shallow; nested patch languages and
Qdrant API compatibility are outside scope.
