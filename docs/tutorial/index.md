# MiniQdrant: A Mechanism-First Tutorial

This book follows one point from the direct API into durable history, immutable
segments, indexes, planning, optimization, and snapshots. Read in order: each
chapter establishes an invariant used by the next. Every mechanism is anchored
to a MiniQdrant source path and function, compared with real Qdrant, and paired
with a repository-tested experiment. MiniQdrant is an educational,
single-process reference implementation—not a Qdrant-compatible server.

## Contents

1. [Meet MiniQdrant](01-getting-started.md) — position, environment, collection
   creation, upsert, and the first search.
2. [Points, Payloads, and Distance](02-points-payload.md) — the value model,
   immutable JSON payloads, validation, and the negative-squared Euclidean
   score.
3. [WAL and Manifest Publication](03-wal-manifest.md) — checksummed frames,
   fsync policies, atomic `CURRENT` publication, and `replay_boundary`.
4. [The Segment Lifecycle](04-segments.md) — mutable-to-immutable flush,
   greatest-version visibility, tombstones, and stable reader handles.
5. [HNSW from Layers to Pruning](05-hnsw.md) — deterministic levels, greedy
   descent, `ef` convergence, degree pruning, and the non-standard restart.
6. [Filtering](06-filtering.md) — payload indexes, `must`/`should`/`must_not`,
   and the candidates-plus-residual contract.
7. [Query Planning](07-planner.md) — cardinality estimates, five strategies,
   and observable plan/work evidence.
8. [Quantization](08-quantization.md) — scalar int8 encoding,
   oversample-and-rescore, and the current full-scan candidate path.
9. [Online Optimization](09-optimizer.md) — merge, vacuum, rebuild, short
   publication locks, late writes, and flush/optimize exclusion.
10. [Snapshots and Methodology](10-snapshots-methodology.md) — SHA-256
    inventories, staged restore, and behavior-matrix-driven engineering.

## How to use the book

Run commands from the repository root with Python 3.12+ and `uv`. Labs use
temporary directories and the direct API unless a chapter explicitly says
otherwise. The [Behavior Matrix](../behavior-matrix.md) is the evidence index;
[Qdrant Mapping](../qdrant-mapping.md) classifies semantic relationships; and
[Differences from Qdrant](../differences.md) defines the claim boundary.

Hands-on exercise solutions are folded in `??? note` blocks. Try the task
first, run its acceptance command, and only then open the reference answer.
Exercises describe patches or temporary scripts but never require changing
`src/` while reading the completed reference repository.
