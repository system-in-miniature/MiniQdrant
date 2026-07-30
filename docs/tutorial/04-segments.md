# Chapter 4 · The Segment Lifecycle

Segments let a vector database separate a short, update-friendly write path
from stable, search-oriented data. That separation creates a correctness
problem: an ID may appear in several segments, a newer delete may cover an
older vector, and an optimizer may replace files while a query still reads
them. MiniQdrant makes these states explicit through versions, tombstones,
stable views, and reference-counted handles.

## Learning objectives

By the end of this chapter, you can:

1. trace records from a mutable segment through flush to an immutable segment;
2. use greatest-version visibility to resolve duplicate point IDs;
3. explain why a tombstone must hide every older live image;
4. describe how `CollectionView` and `SegmentHandle` protect old readers; and
5. distinguish MiniQdrant's segment files from Qdrant's production storage.

## Mutable state: one highest image per ID

`src/miniqdrant/segment/mutable.py::MutableSegment` owns an in-memory dictionary
from canonical point ID to `StoredPoint`, plus payload indexes. Its
`apply_upsert` validates the point, checks the positive version, and ignores
the operation if the same ID already has an equal or newer version. Otherwise
it replaces the stored record and updates payload indexes.

`MutableSegment.apply_delete` uses the same guard. It writes a tombstone with
an empty vector and payload, the supplied version, and `deleted=True`, then
removes the ID from payload indexes. `get` and `iter_live` suppress tombstones,
while `iter_records` includes them for persistence and version resolution.

The mutable segment is not a cache that may be discarded arbitrarily. It is
the current representation of WAL records after the manifest's replay
boundary. It stays memory-resident in this teaching implementation; real
Qdrant has richer appendable segment storage.

## Flush: freeze records and publish an inventory

`Collection.flush` holds both optimizer and update locks. If the mutable
segment is empty it returns. Otherwise it creates a unique segment ID, calls
`SegmentImage.build` with all mutable records, writes the image atomically,
publishes a manifest containing the added ID and current WAL boundary, installs
a `SegmentHandle`, and creates a fresh mutable segment.

`src/miniqdrant/segment/codec.py::SegmentCodec.write_atomic` writes a temporary
directory of component files, fsyncs files and directories, then renames it
into the segment root. The files separate point IDs/vectors, payloads,
versions, deleted IDs, graph data, and payload-index metadata. Despite their
`.bin` names, bodies are framed canonical JSON, not mmap-native Qdrant
formats. `SegmentCodec.read` validates checksums and reconstructs a
`SegmentImage`.

`src/miniqdrant/segment/immutable.py::ImmutableSegment` applies
`_highest_versions` during construction, so even one segment contains at most
one highest image per ID. It builds payload indexes over live points and,
when requested, builds HNSW and optional quantization indexes. Its API does not
mutate records after publication.

Flush with `indexed=False` produces an immutable plain segment. With
`indexed=True`, the image and runtime segment contain an HNSW graph when there
are live points. There is no automatic flush based on
`flush_threshold_points`: the policy module is teaching/test-only and
`Collection` does not call it. This is an important difference from a
background-managed production system.

## Collection-wide visibility

Immutability alone does not settle which record is visible. Consider:

1. segment A contains live point 7 at version 3;
2. segment B contains point 7 with a new vector at version 8;
3. the mutable segment contains a delete tombstone at version 11.

The only visible state is deleted. `collection.py::_latest_records` scans every
published segment and extra mutable record, keeping the record with greatest
version for each ID. `Collection.retrieve` returns a latest record only when
it is not deleted. `Collection.count` counts the same latest map.

Search has an additional trap. A segment-local Top-K may be filled with stale
live versions that collection-level visibility later rejects. Before asking a
segment for candidates, `collection.py::_stale_live_count` counts such stale
records and increases its local limit. Then `_search` accepts a candidate only
if the latest map contains the same version and it is not deleted. This
correctness buffer costs a full scan of segment records per search; it is
explicit teaching code, not a production performance claim.

A tombstone must participate in the greatest-version map even though it never
scores. If deletes were simply removed from the mutable segment, an older
immutable vector would resurrect. Tombstones convert absence into an ordered
historical fact.

### Why local Top-K needs a visibility buffer

Assume the user requests two results. An old segment's best two vectors might
both be stale versions of IDs updated elsewhere. If that segment returns only
two candidates, collection-level checks reject both and cannot recover its
third-ranked, still-visible point. Asking every segment for the user limit is
therefore insufficient when versions overlap.

MiniQdrant computes `_stale_live_count(segment, latest)` and asks for
`limit + stale_count`, capped by the segment's live count. In the worst case,
every stale candidate ranks ahead of every visible candidate, so one extra slot
per stale live record is enough to expose the requested number of possible
visible points. The global collector still keeps only the requested limit.

This reasoning also explains why segment search returns candidate versions.
Matching by ID alone would accept an obsolete score and then project the newest
payload/vector, producing a result assembled from different historical images.
`_search` requires `visible.version == candidate.version`, so score, vector,
payload, and visibility all refer to the same point image.

The solution is intentionally straightforward and expensive. Maintaining an
incremental ID tracker and routing searches around obsolete versions would
avoid rebuilding maps and scanning stale counts on every view. MiniQdrant
chooses an inspectable correctness proof; the mapping document explicitly
prevents readers from interpreting that proof as Qdrant's storage algorithm.

## Stable views and safe reclamation

`Collection.search` does not search the collection's changing segment list
directly. `Collection.capture_view` holds the update lock, acquires every
`SegmentHandle`, snapshots mutable records into a temporary
`ImmutableSegment`, builds the latest-version map, increments active-view
accounting, and returns `CollectionView`.

The view searches exactly that captured tuple. Its context manager releases
handles and decrements active-view accounting on exit. `Collection.close`
waits for active views, so it cannot close owned state beneath an in-flight
reader.

`src/miniqdrant/segment/references.py::SegmentHandle` implements physical file
lifetime. `acquire` increments a protected reference count. `retire` marks the
handle obsolete, but removes its path only if the count is zero. `release`
removes a retired path when the last reader leaves. Logical publication and
physical reclamation are therefore separate events:

```text
new manifest published -> new readers use replacement
old view still open     -> old path remains
old view closes         -> retired path may be deleted
```

This process-local mechanism preserves a stable reader during optimization.
Qdrant's segment holder and proxy segments have broader responsibilities,
including richer concurrent-update mediation.

## Optimization compacts history

`Collection._optimize` captures source handles, their records, mutable records,
and the WAL boundary under the update lock. It then releases that lock for the
long `optimizer/optimizer.py::build_replacement` operation. The replacement
keeps highest versions and can drop tombstones because all captured older
images are being replaced together.

During the long build, new writes may enter the mutable segment. Publication
reacquires the update lock and preserves records whose version is strictly
greater than the captured replay boundary. It publishes a new manifest, swaps
handles and mutable state, and retires source handles. This “short lock, long
build, reconcile late writes” pattern is essential; otherwise an acknowledged
concurrent write could disappear.

`merge()` and `vacuum()` both call the same explicit `optimize()` full rewrite.
They are convenience names, not separate production policies. Chapter 9
studies optimizer policy and concurrency in full; here the important point is
that compaction may remove obsolete images only after newest-version
visibility is preserved.

## MiniQdrant versus real Qdrant

The [mapping table](../qdrant-mapping.md#runtime-and-storage) labels
`MutableSegment`, `ImmutableSegment`, version resolution, codec files, and
`SegmentHandle` as deliberately simplified. The semantic skeleton carries
over: appendable versus stable data, versioned point visibility, tombstones,
immutable publication, stable read guards, and deferred reclamation.

Real Qdrant uses native/mmap and RocksDB-backed components, more sophisticated
segment holders and proxy segments, background optimizers, and incremental ID
tracking. MiniQdrant rebuilds a latest-ID map by scanning records for every
view. It loads all segment data into Python objects. It also writes an HNSW
graph but reconstructs the runtime graph on reopen, a semantically opposite
detail documented in the mapping.

See “Mutable/immutable lifecycle,” “Versions and tombstones,” and “Safe
reclamation” in the [behavior matrix](../behavior-matrix.md#behavior-matrix),
and the storage limitations in [Differences from Qdrant](../differences.md).

## Hands-on lab: watch history disappear safely

```bash
export UV_CACHE_DIR=/tmp/miniqdrant-uv-cache
uv run python - <<'PY'
from pathlib import Path
from tempfile import TemporaryDirectory
from miniqdrant import Database, Distance, Point, SearchRequest

with TemporaryDirectory() as tmp:
    db = Database.open(Path(tmp) / "db")
    c = db.create_collection(
        "items", dimension=2, distance=Distance.DOT
    )
    c.upsert([
        Point(1, (1, 0), {"state": "v1"}),
        Point(2, (0, 1), {}),
    ])
    c.flush()
    c.upsert([Point(1, (2, 0), {"state": "v2"})])
    c.flush()
    c.delete([1])
    print("segments:", c.segment_statistics())
    print("retrieve-1:", c.retrieve([1]))
    print("search:", [
        h.id for h in c.search(
            SearchRequest((1, 0), limit=5, exact=True)
        ).hits
    ])
    c.flush()
    c.optimize()
    print("after-optimize:", c.segment_statistics())
    db.close()
PY
```

Measured output:

```text
segments: SegmentStatistics(segment_count=2, live_points=3, deleted_points=0)
retrieve-1: ()
search: [2]
after-optimize: SegmentStatistics(segment_count=1, live_points=1, deleted_points=0)
```

Before the tombstone is flushed, statistics count physical immutable records:
point 1 appears live in two segments. Logical retrieve and search still obey
the newer mutable tombstone. After flush and optimization, one compact segment
contains only point 2; the captured tombstone and all older images can be
dropped together. This socket-free experiment was run in this repository.

## Exercises

### Understanding

1. Why can physical segment statistics disagree with logical collection count?
2. Why may an optimizer drop a tombstone only when it replaces all covered
   older images?

??? note "Reference answers"

    1. Statistics count records in immutable files, including stale versions.
       Collection count resolves the highest version across immutable and
       mutable state and suppresses tombstones.
    2. If any older segment survives, removing the newest delete fact would
       allow its live vector to reappear. Replacing the complete covered set
       makes the absence safe to encode by omission.

### Hands-on

3. Capture a view, optimize, and test that the view's old segment path exists
   until `view.close()`. Acceptance: use a temporary database, assertions pass,
   and no `src/` edits are made.
4. Upsert the same ID across three flushes and retrieve it. Acceptance: the
   final payload/version is returned before and after reopen.

??? note "Reference solution"

    For exercise 3, record `view.segment_paths`, call `c.optimize()`, assert an
    old path still exists, close the view, then assert the retired old path no
    longer exists. Use at least two source segments so optimization replaces
    them.

    For exercise 4, give payloads `v1`, `v2`, and `v3`. The latest WAL sequence
    must win; reopening must not change that result.

## Summary

A mutable segment stores the newest in-memory images and tombstones. Flush
freezes those records into a checksummed immutable segment and publishes it
through the manifest. Greatest-version resolution prevents stale resurrection,
while stable views and reference-counted handles separate logical replacement
from physical deletion. Chapter 5 adds the approximate HNSW index built over a
segment's live vectors.
