> **Language**: English | [简体中文](docs/zh/ARCHITECTURE.md)

# Architecture

## Runtime ownership

```text
Database
  └─ Collection (update order, current manifest, optimizer, lifecycle)
       ├─ WAL (durable operation sequence)
       ├─ MutableSegment (newest unflushed versions)
       ├─ SegmentHandle[] (published immutable segments)
       ├─ QueryPlanner (per-segment strategy)
       └─ ManifestStore (atomic restart root)
```

`Database` owns collection directories and lifetime. `Collection` is the only
component allowed to order updates or publish a segment set. Indexes never
write storage roots directly.

## Mutation and visibility

An upsert/delete batch is fully validated, appended as one WAL operation, and
only then applied to the mutable segment. Payload replace/merge/key-delete
operations produce a complete new point image and reuse the same upsert WAL
contract. The WAL sequence is its version.
Every read computes the greatest record version per external point ID; a
greatest-version tombstone hides every older image.

```text
validate whole batch → append WAL frame → durability action → apply version
```

Cosine vectors are normalized at validation. All internal metric scores use a
higher-is-better convention, with canonical IDs breaking ties.

## Search

`capture_view()` acquires reference-counted immutable handles and snapshots the
mutable records while holding the short collection lock. Distance work then
runs without that lock.

For each segment, payload indexes yield a candidate set and cardinality
estimate. The planner chooses exact scan, filter-then-exact, HNSW,
filtered-HNSW, or quantized candidate scoring plus exact rescoring. The
collection discards stale segment candidates by version and performs one final
bounded global Top-K.

## Online optimization

```text
capture source handles + WAL version V
→ build replacement outside update lock
→ reacquire update lock
→ retain mutable records newer than V
→ publish one new manifest/CURRENT
→ retire source handles
→ delete source paths after the last old view closes
```

`optimizer/policy.py` contains a deterministic teaching policy: it prioritizes
excessive tombstones, then the two smallest segments above the target count,
then large unindexed segments. That policy is exercised directly by tests but
is not wired into `Collection`: `flush_threshold_points` does not trigger an
automatic flush, and explicit `merge()`, `vacuum()`, and `optimize()` always
force a complete safe rewrite.

## Persistence and recovery

The durable root is `CURRENT`, which names one checksummed manifest. A manifest
names immutable segment directories and a WAL replay boundary. Startup validates
the root and segments, then replays later WAL frames idempotently.

Only an incomplete or checksum-bad active WAL tail may be truncated. Corruption
before the tail is rejected. Snapshot creation first flushes the mutable
segment, copies only manifest-referenced data plus WAL, records SHA-256
checksums, fsyncs, and atomically renames. Restore validates before replacing a
target and opens the staged collection before publication.

## Concurrency model

Updates are serialized per collection. Searchers use stable views. One optimizer
runs at a time, but its expensive build phase does not hold the update lock.
The design is thread-safe for these boundaries; it is not a multi-process
writer protocol.
