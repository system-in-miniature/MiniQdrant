# Chapter 2 · Points, Payloads, and Distance

A vector database stores more than vectors. It needs a stable identity for each
object, metadata for filtering and projection, a metric that defines
similarity, and update rules that say which version is visible. MiniQdrant
collects those concerns in a deliberately small value model. Understanding it
now prevents later confusion: WAL frames, segments, HNSW nodes, filters, and
optimizer rewrites all preserve this same logical point.

## Learning objectives

By the end of this chapter, you can:

1. distinguish `Point`, `StoredPoint`, `SearchRequest`, and `SearchHit`;
2. explain validation and cosine normalization before a WAL append;
3. calculate cosine, dot, and MiniQdrant Euclidean scores;
4. describe full replacement, shallow payload merge, and key deletion; and
5. identify where MiniQdrant's value and payload model differs from Qdrant.

## The point entering the system

`src/miniqdrant/models.py::Point` is the caller-facing mutation value:

```python
@dataclass(frozen=True, slots=True)
class Point:
    id: PointId
    vector: Vector
    payload: FrozenJsonObject = field(default_factory=lambda: freeze_json_object({}))
```

The frozen dataclass prevents rebinding fields, while
`src/miniqdrant/json_values.py::freeze_json_object` recursively converts the
payload into immutable JSON-shaped values. An identifier is canonicalized by
`src/miniqdrant/ids.py::canonicalize_point_id`; MiniQdrant accepts
non-negative 64-bit integers and UUIDs. These restrictions give ordering,
serialization, and equality one stable meaning.

`models.py::validate_point` turns a `Point` into a `StoredPoint`.
`StoredPoint` adds `version` and `deleted`, the two fields needed for
cross-segment visibility. Validation initially assigns version zero. The
mutation path replaces it with the positive WAL sequence in
`MutableSegment.apply_upsert`. A delete uses the same ID and version model but
stores an empty vector, empty payload, and `deleted=True` tombstone through
`MutableSegment.apply_delete`.

This separation is useful: callers describe desired state; storage records
describe an ordered historical image. A `Point` should not choose its own
version, because that would break the one-process monotonic ordering supplied
by the WAL.

### Vector validation and normalization

`models.py::validate_vector` first materializes the sequence as floats, then
checks its dimension, rejects boolean components, and requires every component
to be finite. This happens for every point in `Collection.upsert` before the
update lock appends the batch. One invalid point therefore rejects the whole
batch before durable history is extended.

This ordering gives validation atomicity, not a general transaction. A
ten-point batch either passes preflight validation and becomes one
`UpsertOperation`, or no frame is appended. Failures after the WAL durability
boundary have different semantics: recovery may replay the recorded operation
even when the caller observed an injected process failure. Chapter 3 separates
pre-append rejection, durable acknowledgement, and replay precisely.

For `Distance.COSINE`, `validate_point` calls
`models.py::normalize_cosine`. A zero vector raises `ValueError`, because its
direction and cosine similarity are undefined. A valid vector is divided by
its Euclidean norm and the normalized tuple is stored. Query vectors are
validated and normalized in `MutableSegment.search` and
`ImmutableSegment.search`, so `metrics.py::score` can compute a dot product
for cosine.

For `Distance.DOT`, no normalization occurs. Magnitude contributes to score:
`(2, 0)` scores twice as high as `(1, 0)` against `(1, 0)`. For
`Distance.EUCLID`, `metrics.py::score` returns
`-sum((left-right)**2)`. Identical vectors score negative zero, a vector five
units away scores `-25`, and the higher score still means closer. This is a
ranking score, not Qdrant's usual positive distance presentation.

## Payload: immutable JSON with explicit mutations

Payload connects semantic metadata to a vector. MiniQdrant accepts a JSON
object: string keys with null, boolean, integer, finite float, string, array,
or nested object values. Freezing prevents a caller from mutating a dictionary
after an upsert and silently changing stored state without a WAL record.
`thaw_json` makes a fresh ordinary object when a payload must be transformed
or serialized.

`Collection.replace_payload` replaces the entire payload of every existing
requested point. `Collection.merge_payload` performs a shallow top-level
merge, equivalent to `{**current, **patch}`. It does not recursively merge
nested dictionaries. `Collection.delete_payload_keys` removes named top-level
keys. All three delegate to `Collection._mutate_payload`, which:

1. canonicalizes and deduplicates IDs;
2. resolves the latest visible records;
3. skips missing or deleted points;
4. builds complete new `Point` images with unchanged vectors;
5. validates them; and
6. appends one `UpsertOperation` containing those complete images.

Payload mutation is therefore not a special partial record in the WAL. It is a
new version of the whole point. If no requested live point exists, the method
returns `None` and appends nothing. Otherwise all changed points share the
returned WAL sequence.

### Identity and equality across representations

Point identity is deliberately independent of vector or payload equality.
Upserting the same ID means “publish a newer complete image,” even when the
new vector happens to equal the old one. Two different IDs remain two Top-K
candidates even if every other field matches. This is why version maps,
tombstones, payload indexes, and HNSW nodes key by canonical ID rather than by
object hash or vector bytes.

Integer and UUID IDs share the public type but need deterministic mixed
ordering. `src/miniqdrant/ids.py::point_id_sort_key` supplies a tagged key, and
`point_id_bytes` gives stable bytes for deterministic HNSW levels. These
helpers keep tie-breaking and graph construction reproducible without claiming
that one ID kind is numerically comparable to the other.

Frozen payload equality is structural. Object key order does not create a new
meaning, while array order does. JSON validation rejects unsupported Python
objects and non-finite floats because neither canonical persistence nor filter
comparison should depend on an ad hoc representation. The thaw/freeze cycle in
payload mutations also prevents a transform from retaining caller-owned
mutable aliases.

These rules become cross-cutting invariants. WAL encoding must preserve ID
kind and JSON value; segment codec must restore them; filters must inspect the
same structure; snapshots must checksum the resulting files. A seemingly
small relaxation in the value model would therefore require coordinated
changes throughout the database.

The payload stored on a `SearchHit` is optional. `SearchRequest.with_payload`
defaults to true; `with_vector` defaults to false. `Collection._project_hit`
applies these projection choices only after visibility and Top-K selection.
Turning off payload output changes result materialization, not filtering,
ranking, or stored data.

## Search requests are semantic contracts

`models.py::SearchRequest` deliberately leaves several validations close to
their execution owners. `collection.py::_search` requires a positive limit,
checks that a supplied filter is a `Filter`, and rejects a non-finite score
threshold. Segment search validates the vector against the collection
dimension. A score threshold is applied after stale-version rejection, using
the higher-is-better convention for every distance type.

`SearchHit` contains ID, score, and optional payload/vector. `SearchResult`
contains an immutable tuple of hits and an immutable tuple of plan strings.
Tie-breaking is deterministic: `src/miniqdrant/topk.py::TopK` orders equal
scores by canonical point ID. Determinism makes tests and tutorials
reproducible, although it does not imply that an approximate index visits the
same graph nodes as production Qdrant.

## MiniQdrant versus real Qdrant

The [behavior matrix](../behavior-matrix.md#behavior-matrix) records
“Fixed collection schema,” “Exact deterministic Top-K,” and “Payload
mutation” as separate claims. That separation is important. Correct scoring
does not prove Qdrant-compatible payload behavior, and durable payload updates
do not prove support for Qdrant's vector types.

Real Qdrant supports named dense vectors, sparse vectors, multivectors, richer
payload indexing and conditions, and network schemas for point operations.
MiniQdrant stores exactly one fixed-dimensional dense vector per point.
Its nested field traversal and later filtering rules are educational subsets.
Payload merge and deletion are shallow top-level operations, not Qdrant API
compatibility. Consult the
[`models.py` and `metrics.py` mappings](../qdrant-mapping.md#query-and-indexes)
and [Differences from Qdrant](../differences.md).

The Euclidean distinction deserves special care. MiniQdrant reports negative
squared distance to reuse higher-is-better Top-K and threshold logic. A
threshold of `-9` means “squared distance at most 9,” not “positive distance at
least -9.” Never copy a score threshold between MiniQdrant and a Qdrant
deployment without translating its meaning.

MiniQdrant also stores complete point images for payload edits. Production
Qdrant has richer update APIs and internal storage paths. The common lesson is
that identity, vector, payload, and ordering must produce one unambiguous
visible point; the exact wire and storage representation is deliberately
different.

## Hands-on lab: inspect the value contract

Run from the repository root:

```bash
export UV_CACHE_DIR=/tmp/miniqdrant-uv-cache
uv run python - <<'PY'
from pathlib import Path
from tempfile import TemporaryDirectory
from miniqdrant import Database, Distance, Point, SearchRequest

with TemporaryDirectory() as tmp:
    db = Database.open(Path(tmp) / "db")
    c = db.create_collection(
        "vectors", dimension=2, distance=Distance.EUCLID
    )
    c.upsert([
        Point(1, (0, 0), {"tag": "old"}),
        Point(2, (3, 4), {"tag": "far"}),
    ])
    c.merge_payload([1], {"tag": "new", "year": 2026})
    print("point-1:", dict(c.retrieve([1])[0].payload))
    print("scores:", [
        (h.id, h.score)
        for h in c.search(
            SearchRequest((0, 0), limit=2, exact=True)
        ).hits
    ])
    try:
        c.upsert([Point(3, (1,), {})])
    except ValueError as error:
        print("validation:", error)
    db.close()
PY
```

Measured output:

```text
point-1: {'tag': 'new', 'year': 2026}
scores: [(1, -0.0), (2, -25.0)]
validation: vector dimension must be 2, received 1
```

The merge overwrites `tag` and adds `year`, but it creates a full new point
version internally. Point 1 is identical to the query and point 2 forms a
3-4-5 triangle, so their negative squared scores are `-0.0` and `-25.0`.
Dimension validation reports the collection contract before the invalid batch
can reach the WAL. This direct, socket-free experiment was run in the current
repository.

## Exercises

### Understanding

1. Why must payload freezing happen before the WAL append?
2. For Euclidean scoring, which points pass a threshold of `-10`: squared
   distances 4, 10, and 16?

??? note "Reference answers"

    1. The WAL and stored point must describe a stable value. If caller-owned
       dictionaries remained mutable, state could change without a version or
       durable operation, breaking recovery and visibility.
    2. Distances 4 and 10 score `-4` and `-10`, both at least `-10`.
       Distance 16 scores `-16` and is rejected.

### Hands-on

3. In a temporary script, replace point 1's payload, shallow-merge a nested
   object, and print the result. Acceptance: demonstrate that the nested
   object is replaced rather than recursively merged; do not edit `src/`.
4. Compare cosine and dot collections containing `(1, 0)` and `(2, 0)`.
   Acceptance: assertions show equal cosine scores but different dot scores,
   and the script exits 0.

??? note "Reference solution"

    Exercise 3 can start with `{"meta": {"a": 1, "b": 2}}`, then call
    `merge_payload([1], {"meta": {"a": 9}})`. Accept
    `{"meta": {"a": 9}}`; key `b` does not survive a shallow merge.

    For exercise 4, create separate collections because distance is fixed per
    collection. Search both with `(1, 0)`. Cosine normalizes both stored
    vectors to the same direction; dot preserves magnitudes and scores 1 and
    2.

## Summary

The logical point is a validated ID, vector, and immutable JSON payload; its
stored form adds a WAL-derived version and tombstone state. Cosine normalizes,
dot preserves magnitude, and Euclidean exposes negative squared distance so
one deterministic Top-K can rank every metric. Payload edits become complete
new point versions. Chapter 3 now follows those versions into checksummed WAL
frames, immutable manifests, and restart replay.
