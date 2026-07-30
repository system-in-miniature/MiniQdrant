> **Language**: English | [简体中文](README.zh-CN.md)

# MiniQdrant

[![CI](https://github.com/system-in-miniature/MiniQdrant/actions/workflows/ci.yml/badge.svg)](https://github.com/system-in-miniature/MiniQdrant/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) ![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue.svg)

MiniQdrant is a direct-first Python reference implementation of filtered vector
search, versioned immutable segments, online optimization, and durable recovery.
It is built to expose the mechanisms behind a single-node vector database—not
to reproduce Qdrant's network API or deployment surface.

```text
validated mutation → WAL → mutable segment
                              ↓ flush
query → filter planner → immutable segments → version resolution → global Top-K
                              ↓ optimize
                  HNSW / scalar-quantized segment
```

## What is implemented

- fixed-dimensional dense vectors with cosine, dot-product, or negative squared
  Euclidean scoring;
- immutable JSON payloads, nested filter ASTs, payload field indexes, and
  cardinality-aware per-segment planning;
- versioned full-payload replacement, shallow field merge, and field deletion;
- deterministic exact Top-K and HNSW candidate search;
- scalar-int8 storage with decoded-float candidate scoring, oversampling, and
  exact float rescoring;
- WAL-before-apply upsert/delete operations, monotonic versions, tombstones,
  manifest-rooted restart recovery, and active-tail repair;
- online merge/vacuum/index rebuild, atomic manifest publication, stable read
  views, and reference-counted obsolete segment cleanup;
- checksummed, portable collection snapshots with validate-before-replace
  restore.

The deliberate exclusions are listed in
[DIFFERENCES_FROM_QDRANT.md](DIFFERENCES_FROM_QDRANT.md). The project and its
future course are intentionally separate.

## Quick start

```bash
uv sync
uv run pytest -q
```

Direct API:

```python
from miniqdrant import Database, Distance, Point, SearchRequest

database = Database.open("./demo-data")
collection = database.create_collection(
    "items",
    dimension=3,
    distance=Distance.COSINE,
)
collection.upsert(
    [
        Point(1, (1, 0, 0), {"kind": "book"}),
        Point(2, (0, 1, 0), {"kind": "film"}),
    ]
)
result = collection.search(SearchRequest((1, 0, 0), limit=1))
assert result.hits[0].id == 1
database.close()
```

Thin CLI:

```bash
uv run miniqdrant create ./demo-data items --dimension 3 --distance cosine
uv run miniqdrant upsert ./demo-data items ./points.jsonl
uv run miniqdrant search ./demo-data items '[1,0,0]' --limit 5
uv run miniqdrant payload-index ./demo-data items category keyword
uv run miniqdrant info ./demo-data items
uv run miniqdrant snapshot ./demo-data items ./snapshots/items-001
uv run miniqdrant restore ./snapshots/items-001 ./restored items
```

Each JSONL point has `id`, `vector`, and an optional `payload`.

## Reading map

- [ARCHITECTURE.md](ARCHITECTURE.md): ownership, query, mutation, optimization,
  and recovery flows.
- [docs/behavior-matrix.md](docs/behavior-matrix.md): behavior-to-test evidence.
- [docs/qdrant-mapping.md](docs/qdrant-mapping.md): MiniQdrant modules mapped
  to their closest Qdrant subsystems and semantic relationship.
- [docs/storage-format.md](docs/storage-format.md): WAL, segment, manifest, and
  snapshot formats.
- [DIFFERENCES_FROM_QDRANT.md](DIFFERENCES_FROM_QDRANT.md): exact scope boundary.
- [frozen design](docs/superpowers/specs/2026-07-27-miniqdrant-reference-project-design.md)
  and [implementation plan](docs/superpowers/plans/2026-07-27-miniqdrant-reference-project.md).

## Reliability boundary

An acknowledged mutation has crossed the configured WAL durability boundary.
With the default `always` policy, its frame is fsynced before in-memory apply.
Manifest publication makes a new immutable segment set restart-visible through
`CURRENT`. Search uses greatest-version resolution, so replay and temporary
cross-segment duplicates are idempotent. This is a single-process reference
runtime; it makes no distributed-consistency or replica-acknowledgement claim.

## Trademark Notice

MiniQdrant is an independent educational project. It is not affiliated with, endorsed by, or sponsored by Qdrant Solutions GmbH. "Qdrant" is a trademark of its respective owner.
