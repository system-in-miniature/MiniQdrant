# Chapter 5 · HNSW from Layers to Pruning

Exact search scores every eligible vector. It is simple and authoritative, but
its work grows linearly with segment size. Hierarchical Navigable Small World
(HNSW) indexing trades guaranteed exhaustive work for a graph that tries to
reach strong candidates quickly. MiniQdrant retains the recognizable HNSW
shape while making construction deterministic and inspectable.

## Learning objectives

By the end of this chapter, you can:

1. explain levels, layers, entry point, degree bound, and `ef` breadth;
2. trace insertion through upper-layer descent, neighbor search, and pruning;
3. trace a query from greedy descent to layer-zero convergence;
4. interpret `visited_count` without confusing it with a latency guarantee;
5. state MiniQdrant's non-standard restart and pruning differences honestly.

## A hierarchy of proximity graphs

`src/miniqdrant/index/hnsw.py::HnswIndex` stores vectors, versions, a level per
ID, adjacency maps per layer, deleted IDs, an entry point, and maximum level.
Layer zero contains every point. Higher layers contain progressively fewer
points and act as long-range routing shortcuts. A query descends sparse upper
layers before exploring the dense base layer.

Production HNSW normally samples levels probabilistically. MiniQdrant uses
`hnsw.py::_deterministic_level`: it hashes the point ID together with
`HnswConfig.seed`, then counts low one bits up to level 16. The resulting
geometric-like distribution is stable across runs and insertion order. This
supports reproducible graphs and tests, but is not a claim that Qdrant assigns
the same levels.

`HnswConfig` in `src/miniqdrant/config.py` exposes:

- `m`: maximum retained neighbors per node per layer;
- `ef_construct`: search breadth while selecting insertion neighbors;
- `ef_search`: default layer-zero search breadth;
- `seed`: deterministic level seed.

Its `__post_init__` requires positive `m`, `ef_construct >= m`, and positive
`ef_search`. These are structural guards, not production tuning advice.

Keep construction breadth and query breadth conceptually separate.
`ef_construct` spends work once while shaping connections; a weak graph cannot
always be repaired by an expensive query. `ef_search` spends work for each
request and does not change stored adjacency. Both interact with `m`, data
geometry, filters, and the restart behavior, so tuning one fixture cannot
establish a universal setting. Measure recall against exact search and report
visited work on the actual dataset.

## Construction: navigate, connect, prune

`HnswIndex.__init__` sorts points by canonical ID before calling `_insert`.
The first point becomes the entry point. For each later point, `_insert`
computes its level and creates empty adjacency sets for every occupied layer.

If the current graph has layers above the new point's level, insertion calls
`_greedy` from the top down. `_greedy` repeatedly moves to a neighbor with a
better score; equal scores use stable point-ID ordering via `_better`. This
phase navigates but does not connect the new point.

At each shared layer, `_search_layer` explores from the current entry with
`ef_construct` breadth. The best candidates, ordered by higher score and then
ID, become at most `m` neighbors. Edges are added in both directions.
`_prune` is then applied to the new point and affected neighbors so no retained
adjacency exceeds `m`.

MiniQdrant pruning keeps the `m` closest neighbors and removes reverse edges
for discarded connections. Production HNSW commonly uses a diversity-aware
heuristic: slightly less similar neighbors may provide better routes into
different regions. Nearest-only pruning is shorter and deterministic, but it
can create disconnected or less navigable clusters. This is a deliberate
quality-versus-inspectability trade-off.

If the inserted point has a level above the previous maximum, it becomes the
new entry point and raises `_max_level`. The exported `HnswGraph` freezes the
entry, levels, and sorted adjacency lists so codec and experiments can inspect
the graph without mutating it.

## Search: descend, converge, collect

`HnswIndex.search` validates the positive limit and query dimension and
normalizes a cosine query. Its breadth is
`max(limit, ef_search or config.ef_search)`: HNSW must retain at least enough
candidates to return the requested limit.

Starting at the global entry point, search calls `_greedy` for layers
`max_level` down to 1. The best point found on one sparse layer becomes the
entry for the next denser layer. At layer zero, `_search_layer` performs a
best-first expansion.

`_search_layer` maintains:

- `visited`, so a node is processed at most once;
- `scores`, so candidates need not be rescored;
- a best-first `frontier`; and
- `best`, the current `ef`-sized convergence window.

After popping a frontier candidate, the method sorts the best window. If the
window is full and the next frontier score is worse than its worst member,
expansion stops: no queued path can improve the current bounded set under this
implementation's ordering. Otherwise unvisited neighbors are scored and only
those retained in the best window enter the frontier.

Finally `TopK` excludes marked-deleted nodes and any IDs outside
`allowed_ids`, then returns candidates with their stored versions. Collection
search later performs latest-version and residual-filter checks. An HNSW
candidate is therefore not automatically a visible result.

## The non-standard exhaustive restart

A nearest-only bounded graph may be disconnected. Standard HNSW search starts
from its entry point and does not enumerate every disconnected component.
MiniQdrant adds an explicit loop in `HnswIndex.search`: while it has fewer than
`breadth` scored candidates and unvisited vectors remain, it chooses the
smallest-ID unvisited point and searches that component too.

This restart makes tiny teaching graphs easier to inspect and recall tests less
brittle. It is also non-standard. When components are small or `ef` is large,
the loop can repeatedly restart and visit every vector, turning “approximate”
search into a full scan. A high recall result on such a fixture may measure
this fallback rather than good navigability.

The limitation is stated in the module docstring, the
[`HnswIndex` mapping](../qdrant-mapping.md#query-and-indexes), the
[`Deterministic HNSW`](../behavior-matrix.md#behavior-matrix) row, and
[Differences from Qdrant](../differences.md#other-deliberate-simplifications).
It must remain visible in any benchmark interpretation.

## How a segment selects HNSW

HNSW is built for an immutable segment only when `indexed=True` and the segment
has live points. `src/miniqdrant/segment/immutable.py::ImmutableSegment.search`
creates `SegmentFacts` and asks `QueryPlanner.choose` for a strategy. Exact
requests and small/plain conditions may still select a full scan. A segment
with HNSW can select `hnsw` or a filtered route depending on facts and
configuration.

For graph search, the segment may request more than the final limit when a
filter exists, then applies residual filtering. MiniQdrant's
`FILTERED_HNSW` name is misleading if read as Qdrant parity: it traverses
without true filter-aware graph navigation, oversamples, and post-filters.
Qdrant integrates filtering with graph traversal to avoid recall and latency
failures. This is marked “semantically opposite” in the mapping.

`SearchResult.plan` reveals the selected strategy. `visited_count` is exposed
on low-level HNSW and lab results, although the collection-level
`SearchResult` currently reports plans rather than total visits. Visit count
is deterministic work evidence for a fixed fixture. It is not latency,
throughput, native-memory use, or a production benchmark.

## Persistence caveat

`SegmentImage` can encode `HnswGraph` to `hnsw.bin`, and the codec verifies it
on read. However `SegmentImage.to_segment` constructs a new
`ImmutableSegment`, which rebuilds HNSW from live points instead of installing
the decoded graph. The current deterministic rebuild produces a consistent
teaching index, but persisted-index reuse—the production reason to store the
graph—is absent. The mapping deliberately labels this path “semantically
opposite.”

This matters operationally: a successful reopen proves semantic reconstruction
and validation, not fast index loading. Never infer startup performance from
the presence of `hnsw.bin`.

## MiniQdrant versus real Qdrant

Real Qdrant's HNSW is implemented in optimized systems code and integrated with
segment storage, filter-aware traversal, quantization, background indexing,
production heuristics, and telemetry. MiniQdrant uses Python objects,
deterministic levels and tie-breaking, nearest-only pruning, and exhaustive
component restarts. It reconstructs the graph on open.

The transferable mechanism is still substantial: sparse upper layers navigate
long distances, layer zero refines candidates, `ef` controls a bounded
search/construction window, degree pruning controls graph size, and approximate
candidate generation remains separate from final visibility. The precise
heuristics and performance are not transferable.

## Hands-on lab: inspect a deterministic graph

```bash
export UV_CACHE_DIR=/tmp/miniqdrant-uv-cache
uv run python - <<'PY'
from miniqdrant.config import (
    CollectionConfig, Distance, HnswConfig
)
from miniqdrant.index.hnsw import HnswIndex
from miniqdrant.models import Point, validate_point

cfg = CollectionConfig(
    2, Distance.DOT,
    hnsw=HnswConfig(
        m=2, ef_construct=4, ef_search=3, seed=7
    ),
)
points = [
    validate_point(Point(i, (float(i), 1.0), {}), cfg)
    for i in range(1, 7)
]
index = HnswIndex.build(
    points, distance=cfg.distance, config=cfg.hnsw
)
graph = index.export_graph()
result = index.search((1.0, 0.0), limit=3)
print("entry/max-level:", graph.entry_point, graph.max_level)
print("levels:", sorted(graph.levels.items()))
print("layer-0-degrees:",
      sorted((i, len(n)) for i, n in graph.layers[0].items()))
print("hits:",
      [(c.point_id, c.score) for c in result.candidates])
print("visited:", result.visited_count)
PY
```

Measured output:

```text
entry/max-level: 3 4
levels: [(1, 0), (2, 0), (3, 4), (4, 1), (5, 4), (6, 0)]
layer-0-degrees: [(1, 0), (2, 0), (3, 0), (4, 2), (5, 2), (6, 2)]
hits: [(6, 6.0), (5, 5.0), (4, 4.0)]
visited: 4
```

The seed makes levels and entry point repeatable. Every layer-zero degree is at
most `m=2`; zero-degree nodes reveal disconnected components produced by the
simple pruning rule. Dot scoring against `(1, 0)` ranks larger first
coordinates higher. Search visited four of six nodes—useful inspection data,
not a general performance ratio. This socket-free experiment was run in this
repository.

## Exercises

### Understanding

1. Why can increasing `ef_search` improve recall but increase work?
2. Why is nearest-only pruning more likely to disconnect a graph than a
   diversity-aware heuristic?

??? note "Reference answers"

    1. A larger convergence window retains and expands more alternatives, so a
       promising route is less likely to be discarded early. More retained
       alternatives also mean more scores and node visits.
    2. The nearest neighbors may all point into the same local cluster.
       Diverse neighbors deliberately preserve routes toward other regions,
       even if each is not among the absolutely closest points.

### Hands-on

3. Run the lab with `m=3`. Acceptance: every degree is at most 3, results
   remain sorted by score, and you report whether `visited_count` changed.
4. Run the same fixture twice with seed 7 and once with seed 8. Acceptance:
   exported graphs for equal seeds compare equal; record whether the different
   seed changes levels. Do not edit `src/`.

??? note "Reference solution"

    For exercise 3, change only `m` and ensure `ef_construct >= m`. Assert
    `all(len(n) <= 3 for n in graph.layers[0].values())` and compare the
    measured visit count rather than assuming its direction.

    For exercise 4, place graph construction in a helper accepting `seed`.
    Assert `build(7).export_graph() == build(7).export_graph()`. Compare
    `levels` for seed 8; the hash-derived assignment is deterministic per seed,
    not fixed across seeds.

## Summary

MiniQdrant HNSW builds deterministic hierarchical proximity graphs, descends
upper layers greedily, converges within an `ef` window at layer zero, and
prunes degree to `m`. Its nearest-only pruning and exhaustive disconnected-
component restarts favor inspectability over production behavior, and persisted
graphs are rebuilt on open. Chapter 6 turns from vector navigation to payload
filtering and the candidates-plus-residual contract that must surround it.
