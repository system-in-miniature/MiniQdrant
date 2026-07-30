# Chapter 6: Filtering

> English · [中文版](../zh/tutorial/06-filtering.md)

Vector similarity answers “which points are close?” Payload filtering adds a
second question: “which close points are eligible?” MiniQdrant deliberately
separates these concerns. A filter first becomes a typed condition tree, a
payload index narrows the possible point IDs, and any condition the index
cannot prove is retained as a **residual** predicate. Search is correct only
when the candidate path and residual evaluation agree.

## Learning objectives

By the end of this chapter, you will be able to:

1. construct and predict `must`, `should`, and `must_not` filters;
2. explain MiniQdrant's array-expanding dot-path semantics;
3. trace `PayloadIndexSet.candidates()` from indexed clauses to a residual;
4. distinguish an exact candidate set from a cardinality estimate; and
5. verify that indexed filtering returns the same IDs as a full evaluation.

## 1. From a condition tree to a Boolean decision

The public filter vocabulary is defined in
`src/miniqdrant/filters/ast.py`: `Match`, `Range`, `HasId`, and recursively
nested `Filter`. Their `__post_init__()` methods reject malformed paths,
non-finite numeric values, empty ID sets, contradictory range bounds, and
unsupported condition objects at construction time. This is useful because
the search loop does not need to rediscover basic structural errors.

The definitive Boolean semantics live in
`src/miniqdrant/filters/evaluate.py::matches_filter`:

```python
return (
    all(... for item in filter_.must)
    and not any(... for item in filter_.must_not)
    and (not filter_.should or any(... for item in filter_.should))
)
```

Therefore every `must` clause must match, no `must_not` clause may match, and a
non-empty `should` list requires at least one match. `should` is not merely a
score boost in this teaching implementation. An empty `should` list is
vacuously satisfied.

Field lookup is equally important. In
`src/miniqdrant/filters/evaluate.py::resolve_path`, a dotted path is split and
passed to `_walk_path`. Mappings consume one component; sequences recursively
apply the same remaining path to every element. At the leaf, arrays are
flattened again. Thus `Match("reviews.user", "bob")` can find Bob inside:

```python
{"reviews": [{"user": "alice"}, {"user": "bob"}]}
```

`Match` and `Range` then use “any leaf matches” semantics. A missing path
resolves to no values, so even `Match("missing", None)` is false. Booleans are
also explicitly excluded from numeric ranges, despite Python making `bool` a
subclass of `int`.

This path rule is convenient but creates a subtle correlation loss. The filter
`reviews.user == "alice"` AND `reviews.score >= 5` may be satisfied by two
different array elements. MiniQdrant has no element-local nested condition
operator.

## 2. A payload index proves only what it knows

`src/miniqdrant/filters/index.py::PayloadFieldIndex` supports four schemas:
`keyword`, `integer`, `float`, and `bool`. `upsert()` first removes a point's
old indexed values, resolves the configured path, accepts values compatible
with the schema, and updates an equality map. `range()` can scan the values
held by integer or float indexes; asking a keyword index for a range returns
`None`, meaning “this index cannot answer,” not “there are no matches.”

`PayloadIndexSet` owns the live-ID universe and all field indexes. Its central
method is `PayloadIndexSet.candidates()`:

```python
resolved = self._resolve(filter_, universe)
if resolved.exact:
    return CandidateSet(resolved.ids, exact_count(len(resolved.ids)), True, None)
return CandidateSet(
    resolved.ids,
    CardinalityEstimate(0, len(resolved.ids) // 2, len(resolved.ids), False),
    False,
    filter_,
)
```

An indexed `Match`, an indexed numeric `Range`, or `HasId` can produce an exact
set. An unindexed condition returns the current universe with `exact=False`.
For `must`, exact sets are intersected even if another clause remains
unresolved. This is the useful middle ground: the index narrows work without
claiming that it finished the filter.

Unresolved `should` and `must_not` clauses require special care. An unresolved
`should` cannot safely reduce the candidate set, because an unindexed branch
might admit a point. An unresolved `must_not` cannot safely subtract anything.
`PayloadIndexSet._resolve_filter()` therefore retains a conservative
superset and marks it inexact.

The returned `CandidateSet` carries four facts:

- `ids`: a safe superset of matching live IDs;
- `estimate`: lower, expected, and upper cardinality bounds;
- `exact`: whether `ids` is already the complete answer; and
- `residual`: the original filter when exact proof is unavailable.

For an inexact set, the current heuristic is `[0, N/2, N]`. This is
inspectable teaching arithmetic, not a statistics model.

### A practical debugging order

When a filtered search returns a surprising point, debug from semantics toward
acceleration. First call `matches_filter()` directly with the point ID and
payload. If that result is surprising, inspect `resolve_path()` and remember
that arrays flatten automatically. Next compare the IDs from
`PayloadIndexSet.candidates()` with a comprehension that calls
`matches_filter()` over every live point. Candidate IDs may be a superset, but
they must never omit a true match. Finally inspect `exact` and `residual`: an
inexact candidate set with `residual=None` would be a correctness defect.

Updates create another useful probe. `PayloadFieldIndex.upsert()` begins with
`delete(point.id)`, so replacing `{"kind": "book"}` with
`{"kind": "movie"}` must remove the ID from the book posting set before adding
it to the movie set. `tests/query/test_payload_index.py::test_index_update_removes_old_value`
guards this transition. If stale index membership appears after a collection
update, trace `MutableSegment.apply_upsert()` into its `PayloadIndexSet`, then
check whether the latest-version visibility layer rejected the older point
image. This order separates three distinct bugs: wrong filter semantics, wrong
index maintenance, and wrong cross-segment version visibility.

### Candidate proof as an interface contract

The candidate/residual split gives future index implementations a precise
contract. A new index may return fewer IDs only when it can prove that every
removed ID fails the condition. Otherwise it must keep those IDs and mark the
resolution inexact. Returning a larger superset changes cost but not results;
returning an unjustifiably smaller set is an unrecoverable false negative,
because residual evaluation never sees the missing point.

That distinction shapes tests. An index test should compare its candidate set
with full evaluation and assert that every true match is present. If
`exact=True`, it should additionally assert set equality and
`residual is None`. If `exact=False`, it should run the residual over the
candidate set and compare the final set with full evaluation. Tests should
also repeat after upsert and delete, since a correct static posting list can
still have broken maintenance. This contract lets MiniQdrant add a faster
range structure later without changing filter semantics or planner meaning.

## 3. Where residual evaluation happens

`src/miniqdrant/segment/immutable.py::ImmutableSegment.search` asks the payload
indexes for candidates before it invokes the query planner. If the planner
chooses an exact scan, the segment constructs a `PlainVectorIndex` over the
candidate IDs and passes the residual predicate to
`PlainVectorIndex.search_with_stats()`. On the quantized branch,
`src/miniqdrant/query/executor.py::execute_quantized_rescore` converts the
residual into a `matches_filter()` predicate. On the graph branch,
`ImmutableSegment.search()` checks `matches_filter()` again before returning
the oversampled candidates.

That repeated-looking work is a correctness boundary. Candidate generation is
allowed to be conservative; result admission is not. The invariant is recorded
in the [behavior matrix](../behavior-matrix.md): indexed candidates plus
residual evaluation must equal full evaluation. The direct evidence is
`tests/query/test_payload_index.py::test_payload_index_candidates_equal_scan`
and `test_unindexed_condition_is_retained_as_residual`, while
`tests/query/test_plan_parity.py::test_indexed_and_unindexed_exact_search_return_same_hits`
checks the public search result.

## 4. Compared with real Qdrant

Real Qdrant also models payload filters as a condition tree and uses structured
payload indexes to estimate and narrow candidates. In the Qdrant source tree,
the analogous concepts live around the filter types and structured payload
index under `lib/segment/src/types.rs` and
`lib/segment/src/index/struct_payload_index.rs`. Users create payload indexes
through collection APIs and configure richer types than MiniQdrant's four
schemas.

The similarities stop at the teaching boundary:

- Qdrant supports more field-index families, including text, geo, datetime,
  and storage-backed implementations.
- Qdrant uses explicit array path notation and has nested conditions that keep
  predicates on the same array element. MiniQdrant automatically expands
  arrays and loses that correlation.
- Qdrant combines filtering with production HNSW traversal. MiniQdrant's
  “filtered HNSW” traverses first and post-filters a fixed oversample.
- MiniQdrant's non-exact cardinality estimate is a fixed midpoint heuristic,
  not production statistics.

These are not small syntax differences; they can change which points match and
how much work search performs. See difference 5 in the
[full differences document](https://github.com/system-in-miniature/mini-qdrant/blob/main/DIFFERENCES_FROM_QDRANT.md), the filter and
cardinality rows in the [behavior matrix](../behavior-matrix.md), and the
query/index rows in the [Qdrant mapping](../qdrant-mapping.md).

## 5. Hands-on experiments

Run commands from the repository root. `UV_CACHE_DIR` is set explicitly so the
commands also work in a sandbox whose default uv cache is read-only.

### Experiment A: observe public filtered search

```bash
UV_CACHE_DIR=/tmp/miniqdrant-uv-cache uv run python -m miniqdrant.labs.filtering
```

Measured output:

```text
Filtering lab: query=(1.0, 0.0), tenant='a', limit=10
Matching ids: [1, 3]
Selected plan: ('exact_full_scan',)

Interpretation:
- point 2 is vector-similar but excluded because its tenant is 'b'.
- the payload index lets the public collection API plan a filtered search.
```

The plan is an exact scan because the fixture is small. Filtering still removes
point 2 before it can enter the final Top-K.

### Experiment B: expose candidates and residuals

```bash
UV_CACHE_DIR=/tmp/miniqdrant-uv-cache uv run python - <<'PY'
from miniqdrant import CollectionConfig, Distance, Filter, Match, Point, Range
from miniqdrant.filters.index import PayloadIndexSet, PayloadSchema
from miniqdrant.models import validate_point

config = CollectionConfig(dimension=2, distance=Distance.DOT)
points = tuple(validate_point(point, config) for point in (
    Point(1, (1, 0), {"kind": "book", "price": 10.0}),
    Point(2, (0, 1), {"kind": "movie", "price": 20.0}),
    Point(3, (1, 1), {"kind": "book", "price": 30.0}),
))
indexes = PayloadIndexSet(point.id for point in points)
indexes.create("kind", PayloadSchema.KEYWORD, points)
query = Filter(must=(Match("kind", "book"), Range("price", lte=20.0)))
partial = indexes.candidates(query)
print("kind-only ids:", sorted(partial.ids))
print("exact:", partial.exact, "estimate:", partial.estimate)
print("residual retained:", partial.residual is query)
indexes.create("price", PayloadSchema.FLOAT, points)
complete = indexes.candidates(query)
print("fully indexed ids:", sorted(complete.ids))
print("exact:", complete.exact, "estimate:", complete.estimate)
print("residual:", complete.residual)
PY
```

Measured output:

```text
kind-only ids: [1, 3]
exact: False estimate: CardinalityEstimate(minimum=0, expected=1, maximum=2, exact=False)
residual retained: True
fully indexed ids: [1]
exact: True estimate: CardinalityEstimate(minimum=1, expected=1, maximum=1, exact=True)
residual: None
```

Acceptance check:

```bash
UV_CACHE_DIR=/tmp/miniqdrant-uv-cache uv run pytest -q tests/contract/test_filters.py tests/query/test_payload_index.py
```

Measured output: `15 passed in 0.08s`.

## 6. Exercises

1. **Understanding:** Why must an unindexed `must_not` clause leave the
   candidate universe intact?
2. **Understanding:** Can `reviews.user == "alice"` and
   `reviews.score >= 5` prove that Alice gave a score of five?
3. **Hands-on design:** Propose an `exists(path)` condition. Do not edit
   `src/`; write the AST, scan evaluator, and candidate-resolution changes as a
   patch in a scratch file. Acceptance: your design must make missing paths
   false, array leaves visible, and unindexed existence a residual; list three
   focused test names.

??? note "Reference answers"

    1. Subtracting an unresolved set could remove eligible points. Keeping the
       universe produces a safe superset; the residual later performs the
       exclusion exactly.
    2. No. `_walk_path()` flattens both paths independently, so Alice may occur
       in one object and score five in another. Real Qdrant nested conditions
       provide element-local correlation; MiniQdrant does not.
    3. A suitable scratch patch adds a frozen `Exists(path)` dataclass using
       `_validate_path`, includes it in `Condition`, evaluates it with
       `bool(resolve_path(payload, path))`, and makes `_resolve()` return
       `_Resolved(universe, False)` until an existence index exists. Suggested
       tests are `test_exists_matches_present_null`,
       `test_exists_traverses_array_objects`, and
       `test_unindexed_exists_is_retained_as_residual`. Acceptance is
       `UV_CACHE_DIR=/tmp/miniqdrant-uv-cache uv run pytest -q
       tests/contract/test_filters.py tests/query/test_payload_index.py` after
       applying the scratch patch in a disposable worktree.

## Summary

MiniQdrant filtering is not “look up IDs and hope.” The AST defines Boolean
semantics, path walking defines what a field means, indexes return a provably
safe candidate superset, and residual evaluation closes every proof gap. The
candidate set also supplies cardinality bounds. Chapter 7 follows those bounds
into `QueryPlanner`, where they decide whether a segment scans, filters first,
walks HNSW, or enters the quantized branch.
