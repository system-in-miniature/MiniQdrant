# Chapter 8: Quantization

> English · [中文版](../zh/tutorial/08-quantization.md)

Dense vectors are usually stored as floating-point numbers. Scalar
quantization replaces each component with a small integer code, reducing the
representation used during candidate scoring. The useful production pattern
is two-stage retrieval: use an approximate representation to select more
candidates than needed, then rescore those candidates with original vectors.
MiniQdrant implements that pattern, but its candidate stage is deliberately a
decoded-float full scan. It does not deliver Qdrant's integer scorer or HNSW
acceleration.

## Learning objectives

By the end of this chapter, you will be able to:

1. derive MiniQdrant's per-dimension int8 scale and code;
2. explain constant-dimension handling and the error bound;
3. trace oversampling followed by exact rescoring;
4. prove from source that the quantized branch currently scans all eligible
   codes and bypasses HNSW; and
5. separate recall evidence from storage, latency, and compatibility claims.

## 1. Fitting a scalar quantizer

`src/miniqdrant/index/quantization.py` reserves integer codes from `-128` to
`127`, giving 255 intervals. `ScalarQuantizer.fit()` materializes the training
vectors, rejects empty, ragged, zero-dimensional, or non-finite input, and
computes a minimum and maximum for every dimension.

For a dimension with minimum \(a\) and maximum \(b\), its scale is:

\[
s = \frac{b-a}{255}
\]

If \(a=b\), the scale is zero. Otherwise
`ScalarQuantizer.encode()` calculates:

```python
code = round((number - minimum) / scale) + _MIN_CODE
```

and clamps the result to the int8 range. `decode()` reverses that mapping:

```python
minimum + (code - _MIN_CODE) * scale
```

Rounding to the nearest grid point gives a maximum component error of roughly
half a scale. `ScalarQuantizer.max_error_bound` returns the largest
per-dimension `scale / 2`, but **only for components inside the
`[minimum, maximum]` range used to fit that dimension**. It is not a bound on
dot-product error or final ranking error.

!!! warning "Clamping voids the fitted-range error bound"

    An out-of-range input is clamped to the nearest endpoint code, so its
    reconstruction error is not constrained by `max_error_bound`. For the
    audit counterexample, fitting one-dimensional vectors `[0]` and `[1]`,
    then encoding input `10`, decodes to `1`. The actual component error is
    `abs(10 - 1) = 9.0`, while the reported fitted-range bound is only
    `1 / 510 ≈ 0.00196078`. Treat `max_error_bound` as an in-range
    reconstruction bound, never as a guarantee for arbitrary future inputs.

Constant dimensions deserve explicit treatment. Encoding always emits code
zero, and decoding returns the minimum (which equals the maximum). Without
that branch, fitting would divide by zero. Note that code zero is not the
quantized interval's general midpoint; it is simply a deterministic sentinel
when the dimension has no variance.

## 2. Building the quantized index

`ScalarQuantizedIndex.__init__()` stores a dictionary of the original
`StoredPoint` objects, fits one quantizer over their vectors, and creates one
code tuple per point. Empty indexes are rejected.

`src/miniqdrant/segment/immutable.py::ImmutableSegment.__init__` constructs the
quantized index only when all three conditions hold:

- the segment was built with `indexed=True`;
- `CollectionConfig.quantization` is not `None`; and
- the segment has at least one live point.

It may construct HNSW beside the quantized index, but the two structures are
not composed by the current quantized execution path. Segment persistence also
does not store reusable codes. The
[behavior matrix](../behavior-matrix.md) explicitly says codes are rebuilt on
open.

Configuration is intentionally small.
`src/miniqdrant/config.py::ScalarQuantizationConfig` exposes only a positive
`oversampling` integer, defaulting to four. There are no storage modes,
quantile selection, always-RAM settings, compression ratios, or hardware
scorer controls.

## 3. Approximate candidates, then exact rescore

The core implementation is
`src/miniqdrant/index/quantization.py::ScalarQuantizedIndex.search`.
It first encodes and immediately decodes the query:

```python
approximate_query = self._quantizer.decode(self._quantizer.encode(query))
capacity = min(len(self._points), limit * oversampling)
approximate = TopK(max(1, capacity))
```

Then it loops over **every code** in `self._codes`. Candidate IDs and the
residual predicate can skip points, but every remaining point increments
`visited` and is scored after its code is decoded back into a Python float
tuple. The approximate Top-K retains `limit * oversampling` survivors.

A second `TopK(limit)` reads the original vectors from `self._points` and
scores only those survivors with the original query:

```python
for candidate in approximate.results():
    point = self._points[candidate.point_id]
    rescored.offer(point.id, score(self._distance, query, point.vector))
```

This second pass is why final hit scores can equal exact float scores even
though candidate ordering was approximate. It cannot recover a true nearest
neighbor that quantized scoring failed to place in the oversampled candidate
set. Increasing oversampling generally reduces that risk while increasing
rescore work. If capacity reaches the collection size, all eligible points
survive to exact rescoring and recall becomes exact, at the cost of a full
scan plus another scoring pass.

`src/miniqdrant/query/executor.py::execute_quantized_rescore` is a thin adapter.
It forwards the payload candidate IDs and turns a residual filter into a
predicate. `ImmutableSegment.search()` selects this adapter for
`Strategy.QUANTIZED_HNSW_RESCORE`. It does not pass `self._hnsw` and the
adapter does not accept an HNSW index. That signature-level evidence proves
the graph is bypassed.

An exact request takes a different route. `QueryPlanner.choose()` gives
`exact_requested` highest priority, so the segment uses `PlainVectorIndex`
instead of quantized scoring.

## 4. What the tests establish

`tests/index/test_quantization.py::test_int8_round_trip_has_bounded_error`
checks component reconstruction against `max_error_bound`.
`test_constant_dimension_uses_zero_code_and_round_trips` covers the zero-scale
branch, and parametrized rejection tests cover empty and ragged input.

At the collection level,
`tests/query/test_quantized_rescore.py::test_quantized_candidates_are_rescored_with_original_vectors`
compares returned scores with `metrics.score()` over retrieved original
vectors. `test_exact_request_bypasses_quantized_candidate_scoring` checks plan
selection, and a fixed-seed 200-point experiment requires the minimum recall
across ten queries to remain at least 0.95.

Those tests establish deterministic local behavior for bounded fixtures. They
do not establish compressed memory use on disk, integer arithmetic, latency
speedup, production-scale recall, or Qdrant equivalence.

### Diagnosing recall and score surprises

When approximate and exact hit IDs differ, first confirm that their final
scores are computed from originals. A hit with a quantized reconstruction
score indicates a rescore-path bug; a missing exact neighbor with correct
survivor scores is instead a candidate-recall issue. Increase oversampling in a
scratch experiment. If recall improves, the approximate Top-K discarded the
point. If it does not, compare `allowed_ids` and the residual predicate because
filtering may have excluded it before scoring.

Next inspect scale. One outlier expands a dimension's `[minimum, maximum]`
range, making the grid coarser for the dense central population. The single
global fit has no quantile clipping, so this is expected behavior rather than
numeric corruption. For cosine collections, remember that
`validate_point()` stores normalized vectors and `ImmutableSegment.search()`
normalizes the query before reaching the quantizer; reproducing the index in
isolation with unnormalized inputs changes the experiment.

Finally, use `visited_count` to confirm execution shape. A count equal to all
eligible IDs is expected today. Treating that as an optimization regression
would confuse the documented teaching implementation with the production
design it contrasts against.

### Separate representation, arithmetic, and traversal

“Quantized search” can describe three independent choices that are easy to
collapse. First is **representation**: are stored candidates encoded as small
integers? MiniQdrant does this in memory. Second is **arithmetic**: does scoring
operate directly on integer codes with suitable correction terms? MiniQdrant
does not; it decodes to floats. Third is **traversal**: does an approximate
index avoid scoring every candidate? MiniQdrant does not on this branch; it
iterates the complete eligible code dictionary.

This decomposition makes performance claims testable. Persisting code tuples
would change representation durability but would not create integer scoring.
Replacing decoded scoring with a native int8 kernel could change arithmetic
cost while still scanning every point. Feeding that scorer into HNSW could
change traversal work, but recall and latency experiments would still be
needed. Exact float rescoring remains a fourth, independent decision. The
repository implements one choice from this larger design space, not an
indivisible feature called “quantization.”

## 5. Compared with real Qdrant

Real Qdrant's scalar-quantization implementation is integrated into its vector
storage and scoring stack, around source modules under
`lib/segment/src/vector_storage/quantized/`. Qdrant can retain quantized
representations, use an int8 scorer while traversing HNSW, choose candidates,
and rescore original vectors according to configuration. Its collection
configuration exposes a substantially richer quantization surface.

MiniQdrant preserves only the conceptual pipeline:

```text
fit scalar bins → encode → approximate candidate Top-K
                → oversample → original-float rescore
```

Its runtime behavior is semantically opposite in the performance-critical
middle. It decodes codes back to floats, scans all eligible codes, bypasses
HNSW, and rebuilds codes when opening a persisted segment. The strategy name
contains “HNSW” even though HNSW does not run.

Read differences 2 and 7 in
[`DIFFERENCES_FROM_QDRANT.md`](https://github.com/system-in-miniature/mini-qdrant/blob/main/DIFFERENCES_FROM_QDRANT.md), the scalar
quantization row of the [behavior matrix](../behavior-matrix.md), and the
`ScalarQuantizedIndex` / `execute_quantized_rescore` rows of the
[Qdrant mapping](../qdrant-mapping.md). This is a particularly important
example of why an interface name must not substitute for execution evidence.

## 6. Hands-on experiments

### Experiment A: inspect the quantization grid

```bash
UV_CACHE_DIR=/tmp/miniqdrant-uv-cache uv run python - <<'PY'
from miniqdrant.index.quantization import ScalarQuantizer

vectors = ((-4.0, 2.0), (0.0, 2.0), (7.0, 2.0))
quantizer = ScalarQuantizer.fit(vectors)
probe = (1.25, 2.0)
code = quantizer.encode(probe)
restored = quantizer.decode(code)
print("minima:", quantizer.minima)
print("scales:", tuple(round(x, 6) for x in quantizer.scales))
print("code:", code)
print("restored:", tuple(round(x, 6) for x in restored))
print("max_error_bound:", round(quantizer.max_error_bound, 6))
PY
```

Measured output:

```text
minima: (-4.0, 2.0)
scales: (0.043137, 0.0)
code: (-6, 0)
restored: (1.262745, 2.0)
max_error_bound: 0.021569
```

The first component differs from the probe by about 0.012745, below the
reported half-scale bound. The constant second component round-trips exactly.

### Experiment B: verify reconstruction, rescore, bypass, and recall

```bash
UV_CACHE_DIR=/tmp/miniqdrant-uv-cache uv run pytest -q tests/index/test_quantization.py tests/query/test_quantized_rescore.py
```

Measured output:

```text
.......                                                                  [100%]
7 passed in 2.77s
```

To observe the full-scan consequence next to graph search, rerun the Chapter 7
plan comparison. Its measured quantized row reports `visited=64` for a
64-point segment.

## 7. Exercises

1. **Understanding:** Why does exact rescoring not guarantee exact recall?
2. **Understanding:** What does `max_error_bound` bound, and what does it not
   bound?
3. **Hands-on extension:** Design a persisted `quantization.bin` segment
   component as a scratch diff; do not edit `src/`. Specify metadata, checksum,
   schema validation, and how `SegmentImage.to_segment()` would reuse it.
   Acceptance: list a round-trip test and a corruption test, and state which
   current “codes rebuilt on open” claim would change.

??? note "Reference answers"

    1. Rescoring can reorder only the oversampled survivors. If approximate
       scoring excluded a true top-K point, the exact stage never sees it.
    2. It bounds the worst per-component reconstruction error from this
       quantization grid. It does not bound vector-metric error, rank movement,
       recall, latency, or total memory.
    3. A sound scratch design stores format version, dimension, minima, scales,
       ordered point IDs, and code tuples behind the segment codec's existing
       framed/checksummed publication. Loading validates the collection
       fingerprint, code range, dimensions, and point-ID set before constructing
       `ScalarQuantizedIndex` from trusted fitted state. Tests should be named
       like `test_quantized_codes_survive_segment_round_trip` and
       `test_corrupt_quantization_blob_rejects_open`. Passing them would justify
       changing the behavior-matrix statement that codes are rebuilt on open;
       it would still not prove Qdrant format compatibility.

## Summary

MiniQdrant scalar quantization maps every dimension onto an int8 grid, uses
decoded approximate vectors to collect an oversampled Top-K, and then restores
exact float scores for the survivors. The pipeline teaches candidate/rescore
reasoning, while its full scan and HNSW bypass must remain visible. Chapter 9
moves from query-time approximation to background-style state replacement:
building a compact indexed segment without losing concurrent writes or
deleting files still used by readers.
