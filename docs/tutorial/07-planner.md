# Chapter 7: Query Planning

> English · [中文版](../zh/tutorial/07-planner.md)

A vector index is not automatically the best execution path. A tiny segment
can be cheaper to scan; a highly selective indexed filter can reduce work to a
few exact scores; a large unfiltered segment can justify HNSW. MiniQdrant makes
this decision visible through a five-strategy planner and returns the selected
strategy in `SearchResult.plan`.

## Learning objectives

After this chapter, you will be able to:

1. name all five `Strategy` values and the condition that selects each one;
2. explain why the planner uses the filter estimate's upper bound;
3. trace a public `SearchRequest` to one plan per segment;
4. interpret `SearchResult.plan` and `visited_count` without overclaiming
   performance; and
5. identify where MiniQdrant's fixed planner differs from real Qdrant.

## 1. Planning facts, not point data

`src/miniqdrant/query/planner.py` contains three small data types.
`SegmentFacts` describes the decision inputs: total live points, an optional
`CardinalityEstimate`, HNSW and quantization availability, and an exact-search
override. `SearchPlan` records the chosen `Strategy`, a human-readable reason,
the total, and the estimate. `QueryPlanner` owns two non-negative thresholds.

The planner does not score vectors or evaluate payloads. That separation makes
its behavior deterministic and unit-testable. The ordered decision tree in
`QueryPlanner.choose()` is:

1. `exact_requested` → `EXACT_FULL_SCAN`;
2. a small segment or no HNSW → `EXACT_FULL_SCAN`;
3. filtered maximum at or below the filter threshold →
   `FILTER_THEN_EXACT`;
4. quantization available → `QUANTIZED_HNSW_RESCORE`;
5. any remaining filter → `FILTERED_HNSW`;
6. otherwise → `HNSW`.

Order is policy. An exact request wins over every index. A small segment stays
plain even if it has HNSW and quantization. A selective filter wins before
quantization. Once a large segment reaches step 4, quantization wins over both
filtered and unfiltered graph strategies.

The exact strategy name `QUANTIZED_HNSW_RESCORE` is historically suggestive
but operationally misleading: the current branch never invokes HNSW. Chapter
8 examines that gap.

## 2. Why the upper cardinality bound is the safety input

Chapter 6 introduced `CardinalityEstimate(minimum, expected, maximum, exact)`.
`QueryPlanner.choose()` compares `filtered.maximum` with the exact-scan
threshold, not `expected`.

Suppose an unresolved filter leaves 120 candidates and produces the teaching
estimate `[0, 60, 120]`. A threshold of 100 cannot safely choose
filter-then-exact from the expected value 60: residual evaluation might admit
all 120. Comparing the upper bound ensures the selected exact path is bounded
by the configured worst case. This is conservative planning.

The current estimator in
`src/miniqdrant/filters/index.py::PayloadIndexSet.candidates` is intentionally
crude. Exact indexed results have equal bounds. Inexact results use zero,
half the conservative candidate set, and its full size. The planner teaches
how estimates flow into decisions, not how production histograms are built.

## 3. From `SearchRequest` to per-segment plans

`src/miniqdrant/collection.py::Collection.search` captures a stable
`CollectionView`, whose `search()` calls the module-level
`src/miniqdrant/collection.py::_search`. That function validates the request and asks every
non-empty immutable/mutable snapshot to search independently.

Inside `src/miniqdrant/segment/immutable.py::ImmutableSegment.search`:

1. the query vector is validated and cosine queries are normalized;
2. `PayloadIndexSet.candidates()` supplies IDs and a cardinality estimate;
3. a `QueryPlanner` is constructed;
4. `SegmentFacts` describes this segment;
5. the selected branch executes; and
6. `SegmentSearchResult.strategy` records the plan label.

The collection merges segment results with a global `TopK`, rejects stale
versions and tombstones, applies the score threshold, and returns:

```python
SearchResult(
    hits,
    plan=tuple(result.strategy for result in segment_results),
)
```

Plan observability is therefore per segment. A collection with three published
segments may return three labels. This is not a single global cost-based plan,
nor does it expose an operator tree.

The thresholds have another important source-grounded detail.
`ImmutableSegment.search()` passes
`config.optimizer.indexing_threshold_points` as both `plain_threshold` and
`filter_scan_threshold`. Although `QueryPlanner.__init__()` accepts two knobs,
the runtime currently collapses them to one configuration value.

### Reading the decision tree without ambiguity

For debugging, write the facts beside the branch order rather than jumping
from a plan label to a conclusion. A segment may own HNSW yet select
`EXACT_FULL_SCAN` because it is below the plain threshold. A quantized segment
may select `FILTER_THEN_EXACT` because the filter maximum is small. Conversely,
an unindexed filter may leave a large conservative maximum and send a segment
to `FILTERED_HNSW`. None of those outcomes proves an index is missing.

The reason string in `SearchPlan` is intended for exactly this inspection.
Start with `plan.reason`, then verify `total_points`, `filtered.maximum`,
`has_hnsw`, `has_quantization`, and `exact_requested`. If the facts are wrong,
the fault lies before the planner—usually candidate estimation or segment
construction. If the facts are right but policy is undesirable, change and
test `QueryPlanner.choose()` rather than hiding special cases in the executor.
If the chosen plan is right but results are wrong, follow the corresponding
branch in `ImmutableSegment.search()`. This three-way split—fact construction,
policy selection, execution—keeps a performance-policy discussion from
masking a result-correctness bug.

### Plan stability and configuration changes

A deterministic planner makes configuration experiments reproducible. Given
the same `SegmentFacts` and thresholds, `choose()` always returns the same plan
and reason; no timing sample, cache state, or background statistic refresh is
hidden in the decision. That is excellent for a teaching system, but it also
means configuration changes can create sharp cliffs. A segment growing from
100 to 101 points may move from exact scan to HNSW when the threshold is 100,
even though its workload changed only slightly.

Treat threshold tuning as a hypothesis to test with result parity and measured
work, not as a correctness change. Exact and approximate branches may return
different IDs because HNSW and quantization have recall trade-offs, but
filters, version visibility, score thresholds, and deterministic tie rules
must still hold. When persisting a changed configuration, remember that
`src/miniqdrant/config.py::config_fingerprint` participates in collection and
segment schema checks.
MiniQdrant has no online schema migration, so changing a config in place is not
a supported shortcut to replanning an existing collection.

## 4. What `visited_count` means

Every segment strategy returns a `visited_count`, but it is a branch-specific
work counter:

- exact and quantized scans count eligible vectors scored;
- HNSW counts unique graph nodes visited;
- filtered HNSW counts graph work, not only accepted points.

The public `SearchResult` exposes plan labels but not this count. The lab calls
segment search directly to compare it. Even then, counts are not comparable
CPU costs: a graph visit, decoded-float quantized score, and exact score do
different work.

More importantly, `src/miniqdrant/collection.py::Collection.capture_view` reconstructs
the latest record map by scanning segment records, and
`src/miniqdrant/collection.py::_stale_live_count` scans each segment again to request enough
candidates after stale-version rejection. Thus a low HNSW visit count does not
make end-to-end MiniQdrant search sublinear. Difference 3 in
[`DIFFERENCES_FROM_QDRANT.md`](https://github.com/system-in-miniature/mini-qdrant/blob/main/DIFFERENCES_FROM_QDRANT.md) states this
explicitly.

## 5. Compared with real Qdrant

Real Qdrant performs segment-level query optimization too. Its segment query
optimization and cardinality-estimation code lives around
`lib/segment/src/index/query_optimization/` and the structured payload index.
Production planning considers richer field indexes, index configuration,
segment state, filter structure, hardware-efficient thresholds, and
filter-aware graph mechanisms.

MiniQdrant preserves a useful architectural shape: gather segment facts,
estimate selectivity, select a strategy, execute, and expose evidence. It
deliberately simplifies or reverses several details:

- only five fixed branches exist;
- thresholds are point counts, with the runtime reusing one threshold for two
  decisions;
- inexact cardinality uses a midpoint heuristic;
- filtered HNSW is post-filtering, not filter-aware traversal;
- the quantized plan is a full scan and does not use HNSW;
- `SearchResult.plan` is teaching instrumentation, not Qdrant's telemetry or
  explain API compatibility.

See the cardinality-planning row in the
[behavior matrix](../behavior-matrix.md), differences 1, 2, 3, 7, and 10 in
the [full differences document](https://github.com/system-in-miniature/mini-qdrant/blob/main/DIFFERENCES_FROM_QDRANT.md), and
`QueryPlanner`, `Strategy.FILTERED_HNSW`, and the labs rows in the
[Qdrant mapping](../qdrant-mapping.md).

## 6. Hands-on experiments

### Experiment A: compare four observable execution paths

```bash
UV_CACHE_DIR=/tmp/miniqdrant-uv-cache uv run python -m miniqdrant.labs.plan_comparison
```

Measured output:

```text
Same query: vector=(1.0, 0.0), limit=5
`visited_count` is the plan-specific work counter: scored eligible vectors or unique graph nodes.
    exact | plan=exact_full_scan          | visited= 64 | ids=(0, 1, 63, 2, 62)
     hnsw | plan=hnsw                     | visited= 33 | ids=(0, 1, 63, 2, 62)
 filtered | plan=filtered_hnsw            | visited= 36 | ids=(0, 2, 62, 4, 60)
quantized | plan=quantized_hnsw_rescore   | visited= 64 | ids=(0, 1, 63, 2, 62)

Interpretation:
- exact visits every eligible vector; HNSW follows the graph.
- filtered-HNSW traverses first and filters an oversampled candidate set.
- the quantized plan scans decoded int8 codes, then float-rescores candidates.
- plan names describe planner branches; see DIFFERENCES_FROM_QDRANT.md.
```

The quantized path visiting all 64 points is the key observation: a label is
evidence of a branch, not proof of a production algorithm or speedup.

### Experiment B: verify every planner boundary

```bash
UV_CACHE_DIR=/tmp/miniqdrant-uv-cache uv run pytest -q tests/query/test_planner.py tests/query/test_plan_parity.py
```

Measured output:

```text
........                                                                 [100%]
8 passed in 0.25s
```

`tests/query/test_planner.py::test_planner_boundaries` supplies facts for small,
selective-filter, large-filter, HNSW, quantized, and forced-exact cases.
`test_plan_is_inspectable` checks the reason string. The parity test checks that
planning around an index does not change exact results.

## 7. Exercises

1. **Understanding:** With thresholds of 100, which strategy is selected for a
   10,000-point HNSW segment whose filter estimate is `[0, 40, 80]`?
2. **Understanding:** Why can two segments in one search legitimately report
   different strategies?
3. **Hands-on policy exercise:** In a scratch diff, add a distinct
   `filter_scan_threshold_points` configuration field and wire it to
   `ImmutableSegment.search()`. Do not modify repository `src/`. Acceptance:
   show one unit test where plain threshold is 10 and filter threshold is 100,
   and show the exact command that would run it.

??? note "Reference answers"

    1. `FILTER_THEN_EXACT`, because the conservative maximum 80 is at or below
       100, after the segment has already bypassed the small-segment branch.
    2. Planning is per immutable/mutable segment. Segment sizes, index presence,
       quantization, and filter estimates can differ; `_search()` later merges
       their candidates into one global Top-K.
    3. The scratch diff should add a positive field to `OptimizerConfig`,
       preserve it in config serialization automatically via `asdict`, and pass
       it as `filter_scan_threshold` while retaining
       `indexing_threshold_points` as `plain_threshold`. A focused test should
       assert that 50 unfiltered points scan only if the plain rule allows it,
       while an estimated maximum of 50 selects `FILTER_THEN_EXACT` under the
       independent filter rule. Acceptance command:
       `UV_CACHE_DIR=/tmp/miniqdrant-uv-cache uv run pytest -q
       tests/query/test_planner.py tests/query/test_hnsw_plans.py`.

## Summary

MiniQdrant's planner is intentionally small enough to read as an ordered
decision tree. It consumes conservative segment facts, puts correctness
over optimistic estimates, chooses one of five branches per segment, and
returns plan labels for inspection. The labels must be interpreted alongside
the actual executor. Chapter 8 does exactly that for scalar quantization,
showing where int8 storage, approximate candidate selection, exact rescoring,
and the misleading HNSW label diverge.
