# Chapter 10: Snapshots and Methodology

> English · [中文版](../zh/tutorial/10-snapshots-methodology.md)

A durable collection is not automatically portable. Its current manifest,
referenced segments, metadata, and WAL must travel together, and a restore must
reject corruption before replacing healthy data. MiniQdrant snapshots package
that state behind a SHA-256 file index, publish the package by atomic rename,
and restore through a staged open-and-validate protocol. This final chapter
also turns the repository's behavior matrix into a reusable method for studying
systems in miniature.

## Learning objectives

By the end of this chapter, you will be able to:

1. enumerate the files included in a MiniQdrant collection snapshot;
2. trace snapshot creation through flush, checksum, fsync, and rename;
3. trace restore through checksum validation, staged open, backup, publication,
   and rollback;
4. state the exact atomicity and concurrency claim boundary; and
5. use implementation, direct tests, failure tests, and declared differences
   to evaluate a system claim.

## 1. Establishing a coherent source state

The public entry point is
`src/miniqdrant/collection.py::Collection.create_snapshot`. It first checks the
collection lifecycle and then acquires `_optimizer_lock` and `_update_lock`.
Within that boundary it calls `flush()`, flushes the WAL, and invokes
`create_collection_snapshot()`.

The locks matter. A snapshot must not copy a manifest while an optimizer or
flush is publishing a different generation. Because the locks are reentrant,
`create_snapshot()` can call `flush()` safely. Flushing moves current mutable
records into an immutable segment and advances the manifest's
`replay_boundary`; flushing the WAL establishes the selected local durability
boundary before files are copied.

This does not stop another process from modifying the same collection
directory. MiniQdrant's contract is one process and one writer per collection.

## 2. Creating a checksummed package

`src/miniqdrant/persistence/snapshot.py::create_collection_snapshot` rejects an
existing destination, creates a temporary sibling directory, and copies only
the state reachable from the current manifest:

- `collection.json`;
- `CURRENT`;
- the referenced immutable manifest generation;
- the `wal/` directory; and
- each segment directory named by `manifest.segment_ids`.

Copying referenced segments instead of the entire collection directory avoids
including retired or abandoned paths. The function then walks every file under
the copied `collection/` directory and builds:

```python
files = {
    path.relative_to(collection).as_posix(): _sha256(path)
    for path in sorted(collection.rglob("*"))
    if path.is_file()
}
```

It writes canonical JSON as `snapshot.json` with `format_version=1` and the
relative-path-to-digest map. `_sha256()` streams files in one-megabyte chunks.
`_fsync_tree()` fsyncs files and directories, including the temporary root.
Only after those steps does `os.replace(temporary, destination)` publish the
snapshot, followed by fsync of the destination's parent directory.

If any step before publication fails, the `except BaseException` block removes
the temporary tree. `tests/reliability/test_snapshot_restore_failure.py::test_snapshot_publish_failure_leaves_no_partial_target`
injects `before_snapshot_publish` and verifies that the destination never
appears.

“Atomic snapshot creation” here means a same-filesystem directory rename makes
the completed package visible at one local publication boundary. It does not
mean a distributed transaction or immunity to every filesystem/hardware
failure.

## 3. Validation before restore

`src/miniqdrant/persistence/snapshot.py::validate_collection_snapshot` resolves
the snapshot path and performs validation in layers:

1. parse `snapshot.json` and require format version 1;
2. require the indexed file set to equal the actual collection file set;
3. recompute every SHA-256 digest;
4. load collection metadata and the current manifest;
5. compare the manifest schema fingerprint with
   `config_fingerprint(metadata.config)`; and
6. decode every referenced segment and require its configuration to equal the
   collection configuration.

The exact file-set equality detects both missing and unindexed extra files.
Checksums detect content changes. The later semantic reads detect a
checksummed-but-incoherent package, such as a manifest or segment built for a
different schema. Unexpected parsing and I/O failures are wrapped in
`SnapshotError`, while an existing `SnapshotError` is preserved.

Validation returns the nested `collection/` directory, not a live `Collection`.
Publication belongs to the database layer.

## 4. Staged restore and rollback

`src/miniqdrant/database.py::Database.restore_collection` is a class method so
restore can operate before a target `Database` owns the collection. It
validates the new collection name and calls
`validate_collection_snapshot()` **before** touching an existing target.

The restore protocol is:

1. create a temporary sibling under `database/collections/`;
2. copy the validated collection into staging;
3. rewrite `collection.json` with the requested target name;
4. call `Collection.open(stage)` and close it, forcing normal recovery and
   semantic validation;
5. fsync the staged directory;
6. if replacing, atomically rename the old target to a unique backup;
7. rename staging to the target and fsync the collections directory; and
8. remove the backup only after successful publication.

If target publication fails, the inner exception handler renames the backup
back when possible. The outer handler removes staging. This is why an invalid
or failed restore does not silently destroy the previous collection.

There is an operational precondition: the target database must not have
another writer or an open in-memory `Collection` that continues serving and
mutating the old directory. The code cannot coordinate across processes.
Callers should close the target database before `replace=True`.

## 5. Compared with real Qdrant

Real Qdrant exposes collection and shard snapshot operations through its REST
API, such as creating a collection snapshot and recovering from a snapshot.
Its implementation participates in collection, shard, replica, and distributed
transfer workflows; source responsibilities live around collection snapshot
and storage content-manager modules. Qdrant snapshots use Qdrant's own formats
and operational contracts.

MiniQdrant preserves several recognizable invariants:

- snapshot a coherent published collection state;
- index contents with cryptographic digests;
- build in staging;
- validate before replacement;
- use atomic local publication; and
- roll back the previous target when publication fails.

It omits or changes product behavior:

- the format is private and incompatible with Qdrant;
- only one local collection root is packaged;
- there are no shards, replicas, consensus, remote snapshot storage, API
  authentication, or cluster coordination;
- `replace` assumes no competing writer;
- SHA-256 integrity is not authenticity or encryption; and
- local fsync/rename claims do not imply distributed durability.

See the snapshot row and claim boundary in the
[behavior matrix](../behavior-matrix.md), product-scope snapshot row in the
[full differences document](https://github.com/system-in-miniature/mini-qdrant/blob/main/DIFFERENCES_FROM_QDRANT.md), the snapshot
entry in the [Qdrant mapping](../qdrant-mapping.md), and the concrete tree in
[Storage format](../storage-format.md).

## 6. Hands-on experiments

### Experiment A: inspect and restore a snapshot

```bash
UV_CACHE_DIR=/tmp/miniqdrant-uv-cache uv run python - <<'PY'
from pathlib import Path
from tempfile import TemporaryDirectory
import json

from miniqdrant import Database, Distance, Point, SearchRequest

with TemporaryDirectory() as root:
    root = Path(root)
    db = Database.open(root / "live")
    collection = db.create_collection("items", dimension=2, distance=Distance.DOT)
    collection.upsert([Point(7, (1.0, 0.0), {"kind": "book"})])
    snapshot = collection.create_snapshot(root / "snapshot")
    index = json.loads((snapshot / "snapshot.json").read_text())
    print("format version:", index["format_version"])
    print("indexed file count:", len(index["files"]))
    print("all digests are SHA-256:", all(len(value) == 64 for value in index["files"].values()))
    db.close()
    Database.restore_collection(snapshot, root / "restored-db", "copy")
    restored_db = Database.open(root / "restored-db")
    hits = restored_db.collection("copy").search(SearchRequest((1.0, 0.0), 1)).hits
    print("restored ids:", [hit.id for hit in hits])
    restored_db.close()
PY
```

Measured output:

```text
format version: 1
indexed file count: 11
all digests are SHA-256: True
restored ids: [7]
```

The exact segment directory contains a random UUID, so the experiment reports
stable properties rather than unstable filenames.

### Experiment B: exercise success and failure boundaries

```bash
UV_CACHE_DIR=/tmp/miniqdrant-uv-cache uv run pytest -q tests/reliability/test_snapshot.py tests/reliability/test_snapshot_restore_failure.py tests/acceptance/test_snapshot_roundtrip.py
```

Measured output:

```text
.....                                                                    [100%]
5 passed in 2.28s
```

These tests cover searchable restore, checksum corruption, failed snapshot
publication, failed restore publication with rollback, and portability after
the source database is closed.

## 7. A behavior-matrix method for systems in miniature

A small implementation is valuable when it preserves important mechanisms
without disguising removed layers. MiniQdrant's
[`docs/behavior-matrix.md`](../behavior-matrix.md) evaluates each product goal
with four columns:

1. **implementation boundary** — the public API or symbol that owns it;
2. **direct test** — evidence that the normal behavior works;
3. **failure or quality evidence** — corruption, concurrency, recovery, or
   recall checks; and
4. **scoped difference** — what the evidence does not establish.

Apply that structure to the snapshot claim:

| Question | Repository evidence |
|---|---|
| Where is it implemented? | `create_collection_snapshot`, `validate_collection_snapshot`, `Database.restore_collection` |
| Does the normal path work? | `test_snapshot_restores_searchable_collection`, `test_snapshot_roundtrip_survives_source_removal` |
| What happens at failures? | checksum corruption, pre-publish failure, restore rollback tests |
| What remains out of scope? | Qdrant format/API compatibility, multi-writer and distributed coordination |

This method prevents two common mistakes. First, a class or strategy name is
not proof that the named mechanism ran; Chapter 8's quantized “HNSW” branch is
the counterexample. Second, a passing local test is not evidence for an omitted
production layer; snapshot round-trip does not prove distributed snapshot
coordination.

When extending MiniQdrant, begin with a behavior row before implementation:
name the invariant, owner, direct test, hostile test, and explicit product
boundary. Then implement the smallest source-like architecture that can make
all five statements true. Update the differences and mapping whenever a
previous simplification changes.

## 8. Exercises

1. **Understanding:** Why does a SHA-256 file index detect corruption but not
   prove who created the snapshot?
2. **Understanding:** Why does restore open and close the staged collection
   before publishing it?
3. **Hands-on failure design:** In a scratch diff, add a failure injection
   immediately after the old target is renamed to backup but before staging is
   published. Do not edit `src/`. Acceptance: specify the expected directory
   state, the reopened point IDs, and a test that proves no staging or backup
   residue remains after rollback.
4. **Methodology:** Draft one behavior-matrix row for adding sparse vectors,
   including an honest difference from real Qdrant.

??? note "Reference answers"

    1. A digest binds a path to observed bytes and makes accidental or
       unkeyed content changes detectable. Anyone who can replace both content
       and `snapshot.json` can compute new digests. Authenticity requires a
       trusted signature or MAC and key-management policy.
    2. It reuses the normal `Collection.open()` recovery path to validate WAL,
       manifest, segment codecs, schema, and lifecycle before the directory
       becomes the target. Checksums alone cannot prove those semantic
       relationships.
    3. The existing inner `try` already describes the desired result: on the
       injected failure, rename the backup back to the target, remove staging,
       and leave the original IDs searchable. A focused test can extend
       `test_restore_publish_failure_rolls_back_previous_collection` with
       assertions that `collections/items` contains the original point and no
       `.items-restore-*` or `.items-backup-*` paths remain. Acceptance command:
       `UV_CACHE_DIR=/tmp/miniqdrant-uv-cache uv run pytest -q
       tests/reliability/test_snapshot_restore_failure.py`.
    4. Example: goal “sparse-vector exact retrieval”; owner
       `Collection.search` plus a source-like sparse index boundary; direct
       test against a brute-force sparse dot product; failure/quality evidence
       for malformed indices, duplicate dimensions, restart, and deterministic
       ties; scoped difference “one local sparse vector and exact Python
       scoring, without Qdrant named vectors, hybrid fusion, native sparse
       index, REST/gRPC schema, or distributed shards.”

## Summary

MiniQdrant snapshots capture the manifest-reachable collection state, index
every file by SHA-256, fsync and rename a completed package, validate both bytes
and schema relationships, and restore through a staged normal open with
rollback. The claim is deliberately local and single-writer. Across the whole
tutorial, the enduring method is the same: locate the mechanism owner, make
state transitions explicit, run direct and hostile tests, compare with the
real system, and record what the evidence cannot support. That is how a system
in miniature becomes a trustworthy learning instrument rather than a toy with
production names.
