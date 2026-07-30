# Chapter 1 · Meet MiniQdrant

MiniQdrant is a small, direct-first vector database built for reading. It is
not a Python client for Qdrant, and it is not a production server with a small
configuration. Its purpose is to keep the essential mechanisms of a
single-node vector database close enough that you can follow a write from an
API call to durable storage, and follow a query from a vector to a ranked,
version-correct result.

## Learning objectives

By the end of this chapter, you can:

1. create and reopen a collection through the direct Python API;
2. explain the roles of a database, collection, point, payload, distance, and
   search request;
3. predict why cosine scores rank the two example vectors as they do;
4. locate the code that owns collection lifecycle, validation, and search; and
5. state three important boundaries between MiniQdrant and real Qdrant.

## Why study a teaching kernel?

A production vector database must solve many problems at once: network APIs,
authentication, distributed metadata, replicas, shards, background workers,
storage engines, telemetry, compatibility, and rolling upgrades. Those
features matter, but they can hide the small set of mechanisms we want to
study. MiniQdrant keeps the recognizable data path and removes most deployment
machinery.

The root `README.md` gives the shortest system map:

```text
validated mutation -> WAL -> mutable segment
                               |
                               v flush
query -> per-segment search -> version resolution -> global Top-K
```

This map is not merely documentation. In `src/miniqdrant/database.py`,
`Database.create_collection` validates a name, freezes a
`CollectionConfig`, creates a collection directory, and registers the live
`Collection`. `Database.open` scans collection directories and delegates
recovery to `Collection.open`. The database object therefore owns the
catalogue and lifecycle; the collection owns vectors, mutations, segments, and
search.

The public value model lives in `src/miniqdrant/models.py`. `Point` contains an
integer or UUID identifier, a dense vector, and a JSON payload.
`SearchRequest` carries a query vector, result limit, optional filter and score
threshold, projection flags, exact-mode flag, and optional HNSW breadth.
`SearchResult` returns hits plus the per-segment plan names. That final field is
teaching instrumentation: it lets experiments expose which search route ran.

### Creation fixes the vector space

`Database.create_collection` constructs `CollectionConfig` from `dimension`
and `distance`. `CollectionConfig.__post_init__` in
`src/miniqdrant/config.py` rejects non-positive dimensions and normalizes a
string distance to the `Distance` enum. Once persisted, this schema is not a
per-point suggestion. `src/miniqdrant/models.py::validate_vector` rejects a
wrong dimension, booleans, and non-finite components. `validate_point` also
canonicalizes the ID, freezes the payload, and normalizes a cosine vector.

Cosine normalization is performed at write time by
`models.py::validate_point`, not repeatedly for every stored vector during
search. A cosine query is normalized on the read path. Dot product preserves
the original vector magnitude. Euclidean ranking uses negative squared
distance in `src/miniqdrant/metrics.py::score`, so every metric follows the
same “larger score is better” convention. Chapter 2 examines this value model
in detail.

### A write and a query

`Collection.upsert` in `src/miniqdrant/collection.py` materializes the input
batch, validates every point before performing any write, takes the update
lock, appends one WAL operation, and then applies that record to the mutable
segment. Its return value is the WAL sequence. With default durability, the
WAL frame has crossed a local `fsync` boundary before the in-memory mutation
becomes visible.

`Collection.search` captures a stable `CollectionView` and calls its
`search`. The internal `collection.py::_search` asks each nonempty segment for
candidates, rejects stale versions and tombstoned points, applies the score
threshold, and offers unique visible IDs to `TopK`. Even the first tiny query
therefore uses the same high-level boundaries as a query spanning several
immutable segments.

Notice what is absent: no HTTP request, no serialization round trip, and no
client/server process boundary. This is why the API is called direct-first.
The thin CLI is another adapter over the same objects, not a protocol server.

### How to read the repository

Read by ownership and data flow rather than alphabetically. Start at a public
method such as `Database.create_collection`, `Collection.upsert`, or
`Collection.search`. Follow only the value handed to the next owner. For the
first write, that path is `Point` validation, `Wal.append`,
`Collection._apply_wal_record`, and `MutableSegment.apply_upsert`. For the
first read, it is `Collection.capture_view`, `CollectionView.search`,
`collection.py::_search`, segment search, and `TopK`.

At each boundary, ask four questions: who owns the state, what invariant is
checked, what can fail before publication, and what evidence observes the
result? This prevents a common reading mistake: treating a class name as proof
of production behavior. For example, the presence of `HnswIndex` proves an
implemented graph type, but only its search code, tests, and documented
differences tell us whether traversal matches Qdrant.

Use tests as executable specifications after reading the mechanism, not as a
replacement for it. `tests/contract/` focuses on public state transitions,
`tests/storage/` on encoded structures, `tests/reliability/` on crash
boundaries, and `tests/acceptance/` on end-to-end outcomes. The
[behavior matrix](../behavior-matrix.md) connects retained claims to those
tests. This chapter's small direct experiment is the first end-to-end trace;
later chapters narrow the fixture to expose one internal mechanism at a time.
Keep a scratch diagram of owners and publication boundaries as you read; by
Chapter 10, it will have become a compact model of the entire database.

### Lifecycle is part of correctness

The example closes `Database` explicitly even though its temporary directory
will disappear. That call is not cosmetic. `Database.close` first marks the
catalogue closed, removes its live collection references under the catalogue
lock, and then closes every collection. `Collection.close` coordinates with
optimization and active views, flushes the WAL, and closes the stream.
`src/miniqdrant/lifecycle.py::Lifecycle._ensure_open` makes later operations
fail clearly instead of touching half-closed state.

Context managers are not provided for `Database`, so the caller owns this
boundary. In a longer program, use `try/finally` around the database lifetime.
Do not rely on interpreter shutdown to establish a tested durability point.
Conversely, `Database.simulate_process_loss` exists specifically to avoid the
normal flush path during recovery tests. Calling it is not a faster synonym
for clean close.

Collection creation has a filesystem lifetime too.
`Collection.create` writes checksummed collection metadata, creates the WAL,
and publishes an initial empty manifest before the object is returned.
`Database.drop_collection` closes the live collection before removing its
directory. This process assumes the documented single-writer boundary; another
process holding the same path is outside the safety contract. Thinking about
object lifetime, durable lifetime, and filesystem lifetime separately will
make the later stable-view and snapshot chapters much easier to reason about.

## MiniQdrant versus real Qdrant

Real Qdrant presents REST and gRPC APIs, runs collection and shard services,
coordinates replicas, and uses production storage and indexing components.
MiniQdrant's `Database` is a process-local collection catalogue. Its
`Collection` combines responsibilities that Qdrant distributes across
collection, shard, replica-set, update, and search services. See the
[`Database` and `Collection` mapping](../qdrant-mapping.md#runtime-and-storage).

Three differences matter immediately:

- MiniQdrant has one fixed dense-vector schema per collection. It has no named
  vectors, sparse vectors, or multivectors.
- It provides a Python API and CLI, but no Qdrant-compatible REST or gRPC
  server. A successful direct call proves local semantics, not wire
  compatibility.
- It is a single-process, single-writer reference runtime. “Durable” means the
  selected local WAL policy, not replica acknowledgement or distributed
  consistency.

These are explicit scope decisions, not hidden omissions. The
[`Fixed collection schema`](../behavior-matrix.md#behavior-matrix) and
[`Thin adapters and labs`](../behavior-matrix.md#behavior-matrix) rows name
their tests, while [Differences from Qdrant](../differences.md) lists the
unsupported deployment surface. Throughout this book, use those pages to
separate a carried-over invariant from a production feature.

## Hands-on lab: the first conversation

Run from the repository root. The temporary directory keeps the exercise
repeatable and leaves no database behind.

```bash
export UV_CACHE_DIR=/tmp/miniqdrant-uv-cache
uv run python - <<'PY'
from pathlib import Path
from tempfile import TemporaryDirectory
from miniqdrant import Database, Distance, Point, SearchRequest

with TemporaryDirectory() as tmp:
    db = Database.open(Path(tmp) / "db")
    c = db.create_collection(
        "books", dimension=3, distance=Distance.COSINE
    )
    sequence = c.upsert([
        Point(1, (1, 0, 0), {"title": "Systems"}),
        Point(2, (0, 1, 0), {"title": "Cinema"}),
    ])
    result = c.search(
        SearchRequest((1, 0, 0), limit=2, exact=True)
    )
    print("sequence:", sequence)
    print("hits:", [
        (h.id, round(h.score, 3), h.payload["title"])
        for h in result.hits
    ])
    print("plan:", result.plan)
    db.close()
PY
```

Measured output:

```text
sequence: 1
hits: [(1, 1.0, 'Systems'), (2, 0.0, 'Cinema')]
plan: ('exact_full_scan',)
```

One call produced one WAL sequence. The first stored unit vector is identical
to the normalized query, so its cosine score is `1.0`; the second is
orthogonal, so its score is `0.0`. There is only one in-memory segment view,
and exact mode selected `exact_full_scan`. The payload is returned because
`SearchRequest.with_payload` defaults to true.

This experiment uses no socket and was run in this repository. It exercises
the real direct adapter, validation, WAL append, mutable segment, exact scorer,
version resolution, and Top-K path. It does not exercise a Qdrant client or
server.

## Exercises

### Understanding

1. Why does `Database` own named collections while `Collection` owns search?
2. Why is negative squared Euclidean distance useful even though users often
   expect a positive distance?

??? note "Reference answers"

    1. `Database` is the catalogue and lifecycle boundary. A `Collection`
       owns one fixed vector schema and all of its write, segment, recovery,
       and query state. Keeping those responsibilities separate makes reopen
       and drop operations independent of vector search internals.
    2. All three metrics can use one higher-is-better Top-K implementation.
       Squaring also avoids a square root. The cost is a different
       user-facing score and threshold interpretation, which must be stated.

### Hands-on

3. Without editing `src/`, copy the lab into `/tmp/ch01.py`, change the query
   to `(0, 1, 0)`, and assert that point 2 ranks first. Acceptance: running
   `UV_CACHE_DIR=/tmp/miniqdrant-uv-cache uv run python /tmp/ch01.py` exits
   with status 0 and prints point 2 first.
4. Add a deliberate three-dimensional mismatch to your temporary script.
   Acceptance: catch `ValueError` and print its exact message; the collection
   count must remain 2.

??? note "Reference solution"

    For exercise 3, use
    `SearchRequest((0, 1, 0), limit=2, exact=True)` and
    `assert result.hits[0].id == 2`.

    For exercise 4, call
    `c.upsert([Point(3, (1, 2), {})])` inside `try/except ValueError`, then
    assert `c.count() == 2`. Validation happens before `Wal.append`, so the bad
    batch cannot partially enter the collection.

## Summary

MiniQdrant preserves the educational spine of a vector database: validate a
mutation, log it, apply it to a mutable segment, search segment-local
candidates, resolve versions, and merge a deterministic global Top-K. The
direct API exposes that spine without a network stack, while the mapping and
difference documents keep production claims honest. Next we zoom into points,
payloads, distance metrics, and the exact semantics that every later storage
and index mechanism must preserve.
