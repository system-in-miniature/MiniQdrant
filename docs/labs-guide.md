# Hands-on Labs

> English · [中文版](zh/labs-guide.md)

Install from the repository root:

```bash
uv sync
```

Every lab is deterministic and uses temporary storage where persistence is
needed.

## 1. Payload filtering

```bash
uv run python -m miniqdrant.labs.filtering
```

Expected: `Matching ids: [1, 3]` and a printed selected plan. Point `2` is
vector-similar but excluded because it belongs to tenant `b`. Watch the public
collection API combine vector scoring with a payload-index candidate set.

## 2. Immutable segments and optimization

```bash
uv run python -m miniqdrant.labs.segments
```

Expected:

```text
Segments before optimize: 2
Segments after optimize: 1
```

Each upsert-plus-flush publishes one immutable segment. `optimize()` compacts
the two published segments into one while preserving collection contents.

## 3. Close and reopen recovery

```bash
uv run python -m miniqdrant.labs.recovery
```

Expected: `Restored ids: [1, 2]`. The lab flushes, closes, and opens a new
`Database`, forcing metadata and segment recovery through the public lifecycle
boundary.

## 4. Compare four search plans

```bash
uv run python -m miniqdrant.labs.plan_comparison
```

Expected plan labels are `exact_full_scan`, `hnsw`, `filtered_hnsw`, and
`quantized_hnsw_rescore`, with a `visited_count` beside each. Compare work and
IDs, but read [Differences from Qdrant](differences.md): the quantized branch is
a decoded-int8 full scan plus float rescore despite its teaching plan name.

## 5. HNSW recall

```bash
uv run python -m miniqdrant.labs.recall
```

The fixed seed runs 5 queries over 80 points and prints mean `recall@5`
(currently `1.000` for this fixture). Exact search supplies the reference set;
the metric counts how many exact top-five IDs also appear in HNSW candidates.
This is a reproducible mechanism check, not a production benchmark.

Use the [behavior matrix](behavior-matrix.md) to continue with focused tests,
or run all tests with `uv run pytest -q`.
