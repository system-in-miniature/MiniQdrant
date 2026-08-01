# MiniQdrant Polished Journey Design

## Goal

Expose the finished vector database as three complementary learning modes: the
existing mechanism textbook, a browser-native self-guided reconstruction, and a
concise agent-guided CLI path.

## Historical Stage chain

MiniQdrant has an unusually clean mechanism-first Git history. The Journey keeps
fifteen real, dependency-ordered boundaries rather than inventing source slices:

1. Domain values and collection configuration.
2. Deterministic distance scoring and top-k ordering.
3. Structured payload-filter evaluation.
4. Exact mutable-segment ownership.
5. Public collection operations.
6. Filter-aware query planning.
7. Deterministic HNSW graph search.
8. Versioned immutable segments.
9. Framed write-ahead logging.
10. Manifest publication and restart recovery.
11. Online segment optimization.
12. Scalar quantization with exact rescoring.
13. Atomic snapshot and restore.
14. Flush/optimize mutual exclusion and merge de-duplication.
15. Executable public-API experiments.

Each Stage snapshot is derived from its exact source revision. Consecutive
patches must apply, focused tests must pass at every boundary, and the final
owned source/test tree must byte-match the current branch.

## Lesson and mode contract

Every bilingual Stage explains the current problem, concepts, necessity, and
runtime state before code walkthroughs. Failure previews and test diffs live
inside the Test contract only. Production files are grouped by mechanism;
package exports, fixtures, metadata, and other scaffolding share collapsed
support blocks. Tests are evidence rather than a mandatory test-first script.

The Agent guide only explains how to open Codex and request a Stage. `AGENTS.md`
owns the interactive teaching contract: direct startup from the canonical
repository, resumable marked Stage workspaces, quick misconception screening,
small anchored code slices, focused checks, and cumulative parity. No teaching
branch switch is required.

## Acceptance

Acceptance requires the full test suite, Ruff, compile checks, all fifteen
historical Stage checks, final tree parity, strict MkDocs build, and browser
checks for both languages, collapsed diffs, lesson order, same-Stage language
switching, the three-mode home, and Agent routes.
