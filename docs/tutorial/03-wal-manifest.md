# Chapter 3 · WAL and Manifest Publication

Durability is an ordering claim. MiniQdrant must not expose an acknowledged
point in memory and only later decide whether to record it. It must also avoid
reopening a half-published set of segment files after a crash. The write-ahead
log (WAL), immutable manifest generations, and the `CURRENT` root pointer solve
those two problems at different boundaries.

## Learning objectives

By the end of this chapter, you can:

1. trace an upsert from validation through WAL append to mutable apply;
2. describe the checksummed WAL frame and its tail-repair rule;
3. explain the three local durability policies without overstating them;
4. identify `CURRENT` as the atomic manifest commit point; and
5. derive why `replay_boundary` makes segment state and WAL replay idempotent.

## WAL before apply

`src/miniqdrant/collection.py::Collection.upsert` validates an entire batch,
takes `_update_lock`, and calls `Wal.append(UpsertOperation(batch))` before
`_apply_wal_record`. Delete follows the same order with `DeleteOperation`.
Payload mutations eventually become upserts of complete point images. This is
the central write invariant: no accepted mutation reaches the mutable segment
before its WAL frame is appended under the selected durability policy.

`src/miniqdrant/persistence/wal.py::Wal.append` increments a contiguous
sequence, serializes the operation as canonical compact JSON, wraps it with
`encode_frame`, writes to the active stream, and conditionally calls
`os.fsync`. Only then does it update the in-process last sequence and return a
`WalRecord`. `Collection._apply_wal_record` uses that sequence as the version
for every point in the batch.

One sequence can therefore version several points atomically with respect to
the collection's update lock, but MiniQdrant does not expose a general
transaction protocol. The sequence is an ordering and replay coordinate, not a
distributed timestamp.

### Checksummed frames

`src/miniqdrant/persistence/frame.py::encode_frame` lays out each frame as:

```text
magic | format version | body length | sequence | kind | JSON payload | CRC32
```

The CRC covers sequence, operation kind, and payload. On open,
`frame.py::scan_frames` checks magic, version, maximum size, body boundaries,
CRC, and the minimum body prefix. `wal.py::_validate_sequences` then requires
the frames to be exactly contiguous from sequence 1.

Crash repair is deliberately narrow. An incomplete final frame can be
truncated to the last valid boundary. A checksum-bad final frame can also be
truncated when repair is enabled. A corrupt interior frame is never silently
discarded, because later apparently durable frames would then lose their
history. `_truncate` flushes and fsyncs the repaired length before replay
continues.

This distinction separates a plausible torn append from arbitrary durable
corruption. The WAL does not promise to recover every damaged file; it promises
to repair only the failure shape its append protocol can justify.

## Three local durability policies

`src/miniqdrant/persistence/wal.py::Durability` has three values:

- `ALWAYS`: `Wal.append` fsyncs each frame before returning.
- `INTERVAL`: append writes bytes but this reference runtime has no production
  background interval flusher. A later explicit flush or clean close crosses
  the fsync boundary.
- `MANUAL`: callers rely on `Wal.flush`, collection close, flush/snapshot
  coordination, or their own chosen boundary.

The names teach the trade-off between acknowledgement latency and possible
loss after process or host failure. They are not Qdrant write-consistency
levels and they do not involve replicas. In particular, `INTERVAL` should not
be presented as a complete production scheduler. The
[`WAL-before-apply recovery`](../behavior-matrix.md#behavior-matrix) row says
exactly this.

`Collection.close` waits for owned work, flushes the WAL, and closes it.
`simulate_process_loss` closes without the explicit flush and exists for
reliability experiments. The difference is intentional: ordinary shutdown and
crash simulation must not accidentally have identical persistence behavior.

## Segment publication needs a second commit boundary

The WAL makes recent mutations replayable; immutable segments make older state
quick to load and search. A flush cannot merely write a segment and delete
memory. Recovery needs one authoritative list of complete segments and the WAL
position already represented by them.

`Collection.flush` builds a `SegmentImage` from mutable records, calls
`src/miniqdrant/segment/codec.py::SegmentCodec.write_atomic`, then constructs a
new `Manifest`. The manifest increments generation, preserves the schema
fingerprint, appends the new segment ID, and sets `replay_boundary` to
`Wal.last_sequence`. Only after `ManifestStore.publish` succeeds does the live
collection append the new `SegmentHandle`, install the manifest, and replace
the mutable segment.

`src/miniqdrant/persistence/manifest.py::ManifestStore.publish` uses a
two-stage protocol:

1. encode a checksummed immutable manifest generation, write and fsync a
   temporary file, rename it to its final name, and fsync the directory;
2. write and fsync `CURRENT.tmp`, inject the test failure boundary, replace
   `CURRENT`, and fsync the directory again.

`CURRENT` contains one manifest filename. Its rename is the single publication
commit point. A restart sees either the previous complete generation or the
new complete generation, never a manifest assembled from half old and half new
segment IDs. `Manifest.__post_init__` also rejects duplicate or unsafe segment
IDs, while the schema fingerprint prevents segments from being reopened under
a different collection configuration.

“Atomic” here means a tested same-filesystem rename and publication boundary.
It is not a distributed transaction, and hardware/filesystem guarantees still
matter. The claim boundary is stated under
[Required invariants](../behavior-matrix.md#required-invariants).

## Replay after the manifest boundary

`Collection.open` reads collection metadata, loads `CURRENT`, checks the schema
fingerprint, opens each listed segment, then opens the WAL. It calls:

```python
for record in wal.replay(after_sequence=manifest.replay_boundary):
    collection._apply_wal_record(record)
```

Suppose the manifest contains segment state through sequence 40. Replaying
frames 1–40 would be redundant, while skipping frame 41 would lose an
acknowledged later write. `replay_boundary=40` states precisely which prefix is
already represented, so replay begins at 41.

There is a second layer of idempotence. `MutableSegment.apply_upsert` and
`apply_delete` ignore a record when the same ID already has an equal or newer
version. Immutable construction also keeps the highest version per ID. These
guards prevent duplicate historical images from becoming visible, but they do
not excuse a wrong replay boundary: the manifest must still refer only to
durably published segment state.

### Reason through crash timelines

The easiest way to audit this protocol is to stop it at named boundaries. If a
process dies before `Wal.append`, neither memory nor recovery contains the
operation. Under `ALWAYS`, a death after WAL fsync but before mutable apply may
make the caller observe failure, yet reopen replays the durable frame. That is
why a retry must be treated as a new versioned upsert rather than proof the
first attempt never happened.

During flush, a crash while writing the temporary segment leaves the old
manifest authoritative. A completed segment that is not yet named by a
published manifest is an orphan, not visible state. A crash after the new
manifest file is durable but before `CURRENT` replacement still selects the
old generation. A crash after `CURRENT` replacement selects the new generation
and skips WAL records through its replay boundary.

These outcomes depend on publication order. Cleanup of temporary or orphaned
objects is operational hygiene; it must not be required to decide logical
truth. The root pointer alone decides which complete generation recovery
trusts. Tests in `tests/reliability/test_crash_boundaries.py` and
`test_manifest_publish.py` inject failures around these stages, while
`tests/reliability/test_wal_replay.py` checks replay outcomes. Reading the
failure timeline before the cleanup code is a useful systems habit: first
prove that every crash chooses a valid state, then prove that unused files are
eventually handled.

MiniQdrant intentionally does not reclaim the covered prefix. The WAL directory
contains one file named `00000000000000000001.wal`, and flush only advances the
logical boundary. The file grows forever. Its numbered filename is not proof
of rotation. This explicit difference appears in
[Differences from Qdrant](../differences.md#other-deliberate-simplifications).

## MiniQdrant versus real Qdrant

The architectural lessons carry over: write-ahead ordering, checksums,
monotonic operation ordering, recovery checkpoints, durable file publication,
and a root state that selects a consistent segment inventory. The
[`frame.py`, `wal.py`, Manifest, and replay mapping](../qdrant-mapping.md#runtime-and-storage)
labels these roles as equivalent at the mechanism level.

The operational implementation is much smaller. Real Qdrant manages WAL
capacity and segment persistence within shard machinery, reclaims safely
covered history, integrates background services, and participates in replica
and consensus workflows. MiniQdrant has one unbounded local file, JSON
operations, a custom manifest, one process, and no replica acknowledgement.
Its `INTERVAL` policy is not a production periodic flusher.

Therefore a successful reopen proves the local recovery contract for the
selected policy. It does not prove resilience to every filesystem, storage
device, multi-process writer, or distributed failure. This careful boundary
makes the small experiment valuable rather than misleading.

## Hands-on lab: inspect the durable root

```bash
export UV_CACHE_DIR=/tmp/miniqdrant-uv-cache
uv run python - <<'PY'
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from miniqdrant import Database, Distance, Point

with TemporaryDirectory() as tmp:
    root = Path(tmp) / "db"
    db = Database.open(root)
    c = db.create_collection(
        "items", dimension=2, distance=Distance.DOT
    )
    print("upsert-sequence:",
          c.upsert([Point(1, (1, 2), {"kind": "a"})]))
    c.flush()
    current = (c.path / "CURRENT").read_text().strip()
    envelope = json.loads((c.path / current).read_text())
    payload = envelope["payload"]
    print("current:", current)
    print("manifest:", payload["generation"],
          len(payload["segment_ids"]),
          payload["replay_boundary"])
    print("wal-files:",
          sorted(p.name for p in (c.path / "wal").iterdir()))
    db.close()
    reopened = Database.open(root)
    print("reopened-count:",
          reopened.collection("items").count())
    reopened.close()
PY
```

Measured output:

```text
upsert-sequence: 1
current: manifest-00000000000000000002.json
manifest: 2 1 1
wal-files: ['00000000000000000001.wal']
reopened-count: 1
```

Collection creation published generation 1. Flush published generation 2 with
one segment and a replay boundary of 1. The WAL file remains even though its
first record is covered. Reopen loads that segment and skips the covered frame,
leaving one visible point. The experiment uses no socket and was run in this
repository.

## Exercises

### Understanding

1. Why is `CURRENT` replaced only after the new manifest is durable?
2. Why may a bad final CRC be repairable while a bad interior CRC is fatal?

??? note "Reference answers"

    1. `CURRENT` is the recovery root. Publishing it earlier could point
       restart at an absent or partial generation. The old root must remain
       authoritative until every new referenced object is durable.
    2. A final bad frame can be the residue of the one append interrupted by a
       crash. An interior bad frame has later bytes after it; truncating there
       would silently discard apparently durable later history.

### Hands-on

3. In a temporary script, upsert twice without flushing, close, reopen, and
   print both points. Acceptance: sequences are 1 and 2, reopened count is 2,
   and no `src/` file changes.
4. Copy a temporary WAL, append three junk bytes, and reopen the database.
   Acceptance: reopen succeeds, the junk tail is truncated, and the original
   visible points remain. Work only in the temporary database.

??? note "Reference solution"

    Exercise 3 relies on `Collection.open` replaying records after the initial
    manifest boundary of zero.

    For exercise 4, close cleanly first, record the WAL size, append
    `b"xyz"` with `open(path, "ab")`, then reopen. `scan_frames(...,
    repair_tail=True)` removes the incomplete header. Assert the repaired size
    equals the recorded size and the count is unchanged.

## Summary

The WAL orders every mutation before mutable visibility and detects torn or
corrupt frames. A checksummed immutable manifest describes a complete segment
set, while atomic replacement of `CURRENT` publishes that set. The
`replay_boundary` joins both structures by naming the exact WAL prefix already
represented. Chapter 4 follows the resulting records through mutable flush,
immutable segment visibility, tombstones, and safe reader lifetimes.
