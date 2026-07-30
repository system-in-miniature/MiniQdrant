# Architecture Tour

The canonical architecture document lives at the repository root:
[open the full architecture reference](https://github.com/system-in-miniature/MiniQdrant/blob/main/ARCHITECTURE.md).
This chapter provides the site reading route without duplicating that source.

```text
validated mutation -> WAL -> mutable segment
                                  |
                                flush
                                  v
query -> filter planner -> immutable segments
                                  |
                        version resolution
                                  v
                            global Top-K
```

`Database` owns collection directories and lifetimes. `Collection` is the only
component allowed to order updates or publish a segment set. An upsert/delete
batch is validated as a unit, written to the WAL, then applied with the WAL
sequence as its version.

Search captures reference-counted immutable handles and a mutable snapshot,
chooses a strategy per segment, discards stale versions, and merges candidates
into one deterministic global Top-K. Optimization builds a replacement outside
the update lock, publishes one new manifest, and deletes obsolete segments only
after old readers release them.

Read next:

1. [Qdrant mapping](qdrant-mapping.md) for subsystem correspondence.
2. [Storage format](storage-format.md) for WAL, segment, manifest, and snapshot
   files.
3. [Behavior matrix](behavior-matrix.md) for tests that prove each contract.
