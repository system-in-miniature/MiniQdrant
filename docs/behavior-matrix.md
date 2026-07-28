# Behavior matrix

| Mechanism | Contract | Evidence |
|---|---|---|
| Domain validation | fixed dimension, finite components, immutable JSON, canonical IDs | `tests/unit/test_domain.py` |
| Metric/Top-K | higher is better; deterministic ID tie break | `tests/unit/test_metrics.py`, `test_topk.py` |
| Filter semantics | nested must/should/must-not and indexed/unindexed parity | `tests/contract/test_filters.py`, `tests/query/test_plan_parity.py` |
| Mutable segment | versioned upsert/delete and immediate visibility | `tests/contract/test_mutable_segment.py` |
| HNSW | deterministic graph/search and measured recall | `tests/index/test_hnsw_*.py` |
| Cross-segment reads | greatest version and tombstones win globally | `tests/acceptance/test_cross_segment_search.py` |
| WAL | ordered checksummed frames; only active-tail repair | `tests/storage/test_wal_codec.py`, `tests/reliability/test_wal_*.py` |
| Atomic manifest | `CURRENT` never names a partial root | `tests/storage/test_manifest.py`, `tests/reliability/test_manifest_publish.py` |
| Restart | manifest load plus idempotent WAL replay | `tests/acceptance/test_cross_restart.py` |
| Online optimizer | late writes win; old readers retain files | `tests/concurrency/test_online_optimize.py` |
| Merge/vacuum policy | deterministic choice, obsolete versions/tombstones removed safely | `tests/unit/test_optimizer_policy.py`, `tests/storage/test_merge.py`, `test_vacuum.py` |
| Quantization | bounded int8 error; oversample then exact rescore; recall floor | `tests/index/test_quantization.py`, `tests/query/test_quantized_rescore.py` |
| Snapshot | portable checksummed root; validate and stage before replace | `tests/reliability/test_snapshot*.py`, `tests/acceptance/test_snapshot_roundtrip.py` |
| Lifecycle | idempotent close and closed-resource rejection | `tests/contract/test_lifecycle.py` |
| CLI/labs | adapters use public API and deterministic fixtures | `tests/acceptance/test_cli.py`, `tests/acceptance/test_labs.py` |

Fake and real external-service paths do not exist in this repository: all tests
exercise the actual local persistence and query runtime. Fault tests inject
failures at named local publication boundaries.
