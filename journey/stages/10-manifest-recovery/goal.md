# Stage 10 · Manifest publication and recovery / Manifest 发布与恢复

<!-- journey: chapter=3 tests_added=6 -->

## English

### Goal

Build manifest publication and recovery and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `src/miniqdrant/__init__.py`
- `src/miniqdrant/collection.py`
- `src/miniqdrant/config.py`
- `src/miniqdrant/database.py`
- `src/miniqdrant/persistence/__init__.py`
- `src/miniqdrant/persistence/manifest.py`
- `src/miniqdrant/persistence/metadata.py`
- `src/miniqdrant/segment/codec.py`
- `src/miniqdrant/segment/immutable.py`
- `tests/acceptance/test_cross_restart.py`
- `tests/reliability/test_crash_boundaries.py`
- `tests/reliability/test_manifest_publish.py`
- `tests/reliability/test_restart.py`
- `tests/storage/test_manifest.py`
- `tests/storage/test_segment_codec.py`

### The problem at this point

Segment files, collection metadata, manifest generations, and wal replay need one restart protocol with an atomic publication point.

### Test contract

#### See the failure first

The focused tests force manifest publication and recovery through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

<!-- journey-file: tests/acceptance/test_cross_restart.py -->
<!-- journey-file: tests/reliability/test_crash_boundaries.py -->
<!-- journey-file: tests/reliability/test_manifest_publish.py -->
<!-- journey-file: tests/reliability/test_restart.py -->
<!-- journey-file: tests/storage/test_manifest.py -->
<!-- journey-file: tests/storage/test_segment_codec.py -->
#### Manifest publication and recovery test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The focused tests force manifest publication and recovery through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

##### Key test statement

```python
assert [hit.id for hit in result.hits] == [2]
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is manifest publication and recovery. Segment files, collection metadata, manifest generations, and wal replay need one restart protocol with an atomic publication point.

### Why this mechanism is necessary

Segment files, collection metadata, manifest generations, and wal replay need one restart protocol with an atomic publication point. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

restart opens one complete manifest generation then replays only the ordered WAL suffix not already represented by it.

### Mechanism blocks

<!-- journey-file: src/miniqdrant/collection.py -->
<!-- journey-file: src/miniqdrant/config.py -->
<!-- journey-file: src/miniqdrant/database.py -->
<!-- journey-file: src/miniqdrant/persistence/manifest.py -->
<!-- journey-file: src/miniqdrant/persistence/metadata.py -->
<!-- journey-file: src/miniqdrant/segment/codec.py -->
<!-- journey-file: src/miniqdrant/segment/immutable.py -->
#### Manifest publication and recovery mechanism

##### What it is and why it appears

The central mechanism is manifest publication and recovery. Segment files, collection metadata, manifest generations, and wal replay need one restart protocol with an atomic publication point.

##### Runtime role

restart opens one complete manifest generation then replays only the ordered WAL suffix not already represented by it.

##### Statement understanding

The durable boundary is this: restart opens one complete manifest generation then replays only the ordered WAL suffix not already represented by it.

<!-- journey-file: src/miniqdrant/__init__.py -->
<!-- journey-file: src/miniqdrant/persistence/__init__.py -->
#### Package, fixture, and project support

These files only keep exports, test corpora, dependencies, and the runtime environment reproducible; they are supporting wiring rather than vector-database mechanism logic.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/10-manifest-recovery/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: restart opens one complete manifest generation then replays only the ordered WAL suffix not already represented by it.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 3](https://github.com/system-in-miniature/mini-qdrant/blob/main/docs/tutorial/03-wal-manifest.md)

## 中文

### 目标

实现Manifest 发布与恢复，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `src/miniqdrant/__init__.py`
- `src/miniqdrant/collection.py`
- `src/miniqdrant/config.py`
- `src/miniqdrant/database.py`
- `src/miniqdrant/persistence/__init__.py`
- `src/miniqdrant/persistence/manifest.py`
- `src/miniqdrant/persistence/metadata.py`
- `src/miniqdrant/segment/codec.py`
- `src/miniqdrant/segment/immutable.py`
- `tests/acceptance/test_cross_restart.py`
- `tests/reliability/test_crash_boundaries.py`
- `tests/reliability/test_manifest_publish.py`
- `tests/reliability/test_restart.py`
- `tests/storage/test_manifest.py`
- `tests/storage/test_segment_codec.py`

### 当前遇到的问题

Segment File、Collection Metadata、Manifest Generation 与 WAL Replay 需要统一的重启协议和原子发布点。

### 测试契约

#### 先看会坏在哪里

聚焦测试让Manifest 发布与恢复经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

<!-- journey-file: tests/acceptance/test_cross_restart.py -->
<!-- journey-file: tests/reliability/test_crash_boundaries.py -->
<!-- journey-file: tests/reliability/test_manifest_publish.py -->
<!-- journey-file: tests/reliability/test_restart.py -->
<!-- journey-file: tests/storage/test_manifest.py -->
<!-- journey-file: tests/storage/test_segment_codec.py -->
#### Manifest 发布与恢复测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

聚焦测试让Manifest 发布与恢复经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

##### 关键测试语句

```python
assert [hit.id for hit in result.hits] == [2]
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是Manifest 发布与恢复。Segment File、Collection Metadata、Manifest Generation 与 WAL Replay 需要统一的重启协议和原子发布点。

### 为什么需要这个机制

Segment File、Collection Metadata、Manifest Generation 与 WAL Replay 需要统一的重启协议和原子发布点。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

重启只打开一个完整 Manifest Generation，再回放其中尚未表示的有序 WAL 后缀。

### 机制板块

<!-- journey-file: src/miniqdrant/collection.py -->
<!-- journey-file: src/miniqdrant/config.py -->
<!-- journey-file: src/miniqdrant/database.py -->
<!-- journey-file: src/miniqdrant/persistence/manifest.py -->
<!-- journey-file: src/miniqdrant/persistence/metadata.py -->
<!-- journey-file: src/miniqdrant/segment/codec.py -->
<!-- journey-file: src/miniqdrant/segment/immutable.py -->
#### Manifest 发布与恢复机制

##### 是什么，为什么现在需要

核心机制是Manifest 发布与恢复。Segment File、Collection Metadata、Manifest Generation 与 WAL Replay 需要统一的重启协议和原子发布点。

##### 在运行时做什么

重启只打开一个完整 Manifest Generation，再回放其中尚未表示的有序 WAL 后缀。

##### 关键语句理解

真正要守住的边界是：重启只打开一个完整 Manifest Generation，再回放其中尚未表示的有序 WAL 后缀。

<!-- journey-file: src/miniqdrant/__init__.py -->
<!-- journey-file: src/miniqdrant/persistence/__init__.py -->
#### 包、Fixture 与工程支撑

这些文件只保持包导出、测试语料、依赖与运行环境可复现，不把支撑接线误讲成向量数据库机制。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/10-manifest-recovery/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：重启只打开一个完整 Manifest Generation，再回放其中尚未表示的有序 WAL 后缀。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 3 章](https://github.com/system-in-miniature/mini-qdrant/blob/main/docs/zh/tutorial/03-wal-manifest.md)
