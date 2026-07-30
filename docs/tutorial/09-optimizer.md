# Chapter 9: The Optimizer

> English · [中文版](../zh/tutorial/09-optimizer.md)

Segments accumulate old point versions and tombstones as updates continue.
Indexes may also need rebuilding. An optimizer turns a captured set of records
into a compact replacement, but the difficult part is not sorting or copying:
it is publishing that replacement while writes and readers continue. MiniQdrant
teaches this as a short-lock/long-build/short-lock protocol with late-write
preservation and reference-counted reclamation.

## Learning objectives

By the end of this chapter, you will be able to:

1. distinguish merge, vacuum, and index policy decisions;
2. trace `Collection._optimize()` across capture, build, publication, and
   reclamation;
3. explain why the captured WAL boundary protects acknowledged late writes;
4. explain why retired segment paths outlive old `CollectionView` objects; and
5. state which optimizer-looking configuration and policy are not wired into
   runtime automation.

## 1. Policy vocabulary versus runtime behavior

`src/miniqdrant/optimizer/policy.py` defines four `OptimizationKind` values:
`VACUUM`, `MERGE`, `INDEX`, and `NONE`. `SegmentCandidate` exposes live count,
deleted count, total count, and deleted ratio. `choose_optimization()` applies
three deterministic rules in order:

1. vacuum the candidate with the greatest qualifying deleted ratio;
2. if there are too many segments, merge the two smallest;
3. index the largest qualifying plain segment; otherwise do nothing.

This function is useful for teaching and unit tests, but it is **not called by
`Collection`**. `OptimizerConfig.flush_threshold_points` also does not trigger
an automatic flush. Public `Collection.merge()`, `vacuum()`, and `optimize()`
all call the same `optimize()` method, and the implementation rewrites the full
captured segment set with `drop_tombstones=True`.

Consequently, the three public verbs do not currently select three distinct
algorithms. This is recorded as difference 10 in
[`DIFFERENCES_FROM_QDRANT.md`](https://github.com/system-in-miniature/mini-qdrant/blob/main/DIFFERENCES_FROM_QDRANT.md) and as
“semantically opposite” in the [Qdrant mapping](../qdrant-mapping.md).

## 2. Building one replacement image

`src/miniqdrant/optimizer/optimizer.py::select_latest` scans records and keeps
the greatest version for each external point ID.
`build_replacement()` then calls `SegmentImage.build()` with those latest
records, optionally removing tombstones, copying payload-index schemas, and
setting `indexed=True`.

That one function combines three conceptual operations:

- **merge:** many source segment images become one;
- **vacuum:** obsolete versions and, when requested, tombstones disappear;
- **rebuild/index:** payload structures, HNSW, and configured quantization are
  built into the replacement segment image.

The replacement is not yet visible. `SegmentCodec.write_atomic()` writes it
under a new segment ID, and visibility changes only when a later manifest is
published.

## 3. Short lock, long build, short lock

`src/miniqdrant/collection.py::Collection.optimize` serializes optimizers with
`_optimizer_lock` and delegates to `_optimize()`. The latter has two critical
sections separated by an unlocked build.

### Capture under the update lock

The first `with self._update_lock`:

- acquires every current `SegmentHandle`;
- copies all immutable and mutable records into `captured_records`; and
- records `replay_boundary = self._wal.last_sequence`.

After that block, writers may acquire `_update_lock` and append newer WAL
records while the optimizer builds. The acquired handles keep source paths
alive.

### Build outside the update lock

`build_replacement()` and `SegmentCodec.write_atomic()` run without the update
lock. This is the “long build” phase. Search can capture views and writes can
advance, rather than waiting for index construction. Tests can pause this phase
deterministically with
`src/miniqdrant/optimizer/failures.py::OptimizationGate`.

### Publish under the update lock

The optimizer reacquires `_update_lock`, computes any segments not present in
the captured source set, and builds a new `Manifest`. Crucially, it preserves:

```python
late_records = tuple(
    record
    for record in self._mutable.iter_records()
    if record.version > replay_boundary
)
```

The replacement contains state at or before the boundary. Strictly newer
records become the next mutable segment. Only after both replacement and
late-record state exist does `ManifestStore.publish()` make the generation
current. The collection then swaps segment handles, manifest, and mutable
state, and retires the old handles.

The WAL sequence is doing double duty as mutation version and capture
boundary. If the optimizer simply reset `_mutable`, an acknowledged write that
arrived during the long build could disappear at publication.

## 4. Readers and delayed reclamation

`src/miniqdrant/collection.py::Collection.capture_view` acquires all current
segment handles while holding `_update_lock`, snapshots mutable records, and
constructs a latest-version map. The view searches exactly those segments even
if optimization publishes a new generation.

`src/miniqdrant/segment/references.py::SegmentHandle` protects physical paths.
`acquire()` increments a reference count. `retire()` marks the handle obsolete
but deletes its directory only when the reference count is zero. `release()`
performs deferred deletion when the final old reader closes.

This separates **logical retirement** from **physical reclamation**. Without
it, publication could make an in-flight view dereference files that had just
been removed. The mechanism is process-local; it is not an epoch-based,
distributed, or crash-recoverable reclamation system.

`Collection.close()` also waits on `_active_views`, while `_optimizer_lock`
prevents close, flush, snapshot creation, and optimization from racing through
incompatible publication boundaries. In particular, `flush()` acquires
`_optimizer_lock` before `_update_lock`, so a flush begun during an optimization
build waits instead of publishing overlapping state.

## 5. Failure atomicity

If manifest publication fails, `_optimize()` removes an unpublished manifest
file, `CURRENT.tmp`, and the new segment directory. The old in-memory segment
set remains current. `tests/reliability/test_optimizer_publish.py::test_failed_optimizer_publish_keeps_old_segments_searchable`
injects a failure before the `CURRENT` replacement and checks exactly that.

If publication succeeds, old handles are retired and eventually removed. The
manifest pointer is the commit record: a fully written replacement directory
without a current manifest is not searchable state.

This is local filesystem atomicity, not a transaction across machines. The
[behavior matrix](../behavior-matrix.md) names temp files, fsync, and `CURRENT`
replacement as the evidence boundary.

### Debugging by publication stage

Optimizer failures become much easier to reason about when classified by the
last completed stage. Before `sources_captured`, no replacement state exists.
During build, current readers and writers should still see the old generation;
a failure should remove only the unpublished new directory. After the segment
is written but before `ManifestStore.publish()`, the new path is an orphan
candidate, not current state. After `CURRENT` is replaced, the new manifest is
the recovery authority and old paths may only remain because views reference
them.

For a “lost write” report, record the late operation's WAL sequence and the
captured `replay_boundary`. A sequence greater than the boundary must appear in
`next_mutable`; an older or equal sequence must be in the replacement image.
For an unexpected missing path, inspect `SegmentHandle` reference count and
retirement timing rather than the planner or WAL. For a blocked flush, inspect
`_optimizer_lock`: waiting during the long build is intentional in this
implementation, even though ordinary upserts can proceed through
`_update_lock`.

`OptimizationGate` makes these states reproducible without sleeps. Tests wait
for the named `sources_captured` event, perform the concurrent action, and
release `finish_build`. That is more reliable than hoping thread scheduling
lands in the vulnerable interval.

## 6. Compared with real Qdrant

Real Qdrant has distinct vacuum, merge, and indexing optimizers under source
modules such as `lib/collection/src/collection_manager/optimizers/`. Optimizer
workers use configuration and segment conditions to schedule background work.
Proxy segments and change tracking reconcile updates while a replacement is
built; segment holders manage a richer searchable segment set.

MiniQdrant preserves the concurrency lesson but simplifies nearly every scale
dimension:

- optimization is explicitly invoked, never automatically scheduled;
- all public optimizer verbs perform one full rewrite;
- the policy function is test-only dead code at runtime;
- one process and one writer own the collection;
- late records are recovered by a simple WAL-boundary comparison;
- reference counting protects readers only inside the current process; and
- replacement always builds an indexed segment rather than choosing a focused
  optimizer operation.

See the online optimization and safe reclamation rows in the
[behavior matrix](../behavior-matrix.md), optimizer differences in the
[full differences document](https://github.com/system-in-miniature/mini-qdrant/blob/main/DIFFERENCES_FROM_QDRANT.md), and the
`build_replacement`, `choose_optimization`, and `_optimize` rows in the
[Qdrant mapping](../qdrant-mapping.md).

## 7. Hands-on experiments

### Experiment A: compact two segments

```bash
UV_CACHE_DIR=/tmp/miniqdrant-uv-cache uv run python -m miniqdrant.labs.segments
```

Measured output:

```text
Segments lab: two upsert+flush rounds followed by optimize
Segments before optimize: 2
Segments after optimize: 1

Interpretation:
- each flush publishes an immutable segment, so the count first reaches two.
- optimize compacts those segments into one while preserving collection contents.
```

This proves the visible compaction effect, not the concurrency invariants by
itself.

### Experiment B: run merge, vacuum, concurrency, and publish failures

```bash
UV_CACHE_DIR=/tmp/miniqdrant-uv-cache uv run pytest -q tests/storage/test_merge.py tests/storage/test_vacuum.py tests/concurrency/test_online_optimize.py tests/reliability/test_optimizer_publish.py
```

Measured output:

```text
......                                                                   [100%]
6 passed in 2.28s
```

The six tests cover newest-version retention, tombstone removal, a write during
the build, flush serialization, an old reader that outlives replacement, and a
failed manifest publication.

## 8. Exercises

1. **Understanding:** Why is `version > replay_boundary`, rather than
   `>=`, the late-write test?
2. **Understanding:** Why can the optimizer retire a handle immediately but
   not necessarily delete its path immediately?
3. **Hands-on concurrency design:** In a scratch diff, change `merge()` and
   `vacuum()` to pass an explicit `drop_tombstones` intent while preserving one
   `_optimize` publication protocol. Do not edit `src/`. Acceptance: name tests
   proving merge retains needed tombstones, vacuum removes safe tombstones,
   late writes win in both modes, and old views remain readable.

??? note "Reference answers"

    1. Records at the captured boundary are already included in
       `captured_records` and therefore the replacement image. Retaining them
       again would duplicate state. Only strictly newer versions arrived after
       the captured snapshot.
    2. Retirement removes a segment from future generations. Existing views
       have acquired references to the old handle and must finish safely;
       `release()` deletes the path only after the final reference reaches zero.
    3. A clean scratch design adds a `drop_tombstones` parameter to
       `_optimize()` and `build_replacement()` calls, with `vacuum()` passing
       true and `merge()` choosing the documented safety rule. The manifest,
       boundary, late-record, and handle-retirement code remains shared.
       Suggested acceptance tests are
       `test_merge_tombstone_prevents_resurrection`,
       `test_vacuum_drops_tombstone_after_full_capture`,
       parametrized `test_late_write_wins_by_mode`, and
       `test_old_view_survives_replacement_by_mode`. Run them with
       `UV_CACHE_DIR=/tmp/miniqdrant-uv-cache uv run pytest -q
       tests/storage tests/concurrency/test_online_optimize.py`.

## Summary

MiniQdrant optimization is an atomic state-replacement protocol: capture a
versioned source set under a short lock, build a compact indexed image without
the update lock, preserve post-boundary writes, publish one manifest, and delay
file deletion until old views release their handles. Its policy-shaped module
is not runtime automation, and its public optimizer verbs currently share one
full rewrite. Chapter 10 reuses the same publication discipline at a larger
boundary: package an entire collection into a checksummed snapshot, validate it
in staging, and restore it without replacing a healthy target on failure.
