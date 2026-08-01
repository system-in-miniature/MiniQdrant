# Stage 13 · Atomic snapshot and restore / 原子 Snapshot 与 Restore

<!-- journey: chapter=10 tests_added=3 -->

## English

### Goal

Build atomic snapshot and restore and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `src/miniqdrant/collection.py`
- `src/miniqdrant/database.py`
- `src/miniqdrant/persistence/snapshot.py`
- `tests/acceptance/test_snapshot_roundtrip.py`
- `tests/reliability/test_snapshot.py`
- `tests/reliability/test_snapshot_restore_failure.py`

### The problem at this point

Portable backups need a self-consistent cut of metadata, manifests, segments, and wal that restores without aliasing the live collection.

### Test contract

#### See the failure first

The focused tests force atomic snapshot and restore through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

<!-- journey-file: tests/acceptance/test_snapshot_roundtrip.py -->
<!-- journey-file: tests/reliability/test_snapshot.py -->
<!-- journey-file: tests/reliability/test_snapshot_restore_failure.py -->
#### Atomic snapshot and restore test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The focused tests force atomic snapshot and restore through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

##### Key test statement

```python
assert [hit.id for hit in restored.search(SearchRequest((1.0, 0.0, 0.0), 2)).hits] == [
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is atomic snapshot and restore. Portable backups need a self-consistent cut of metadata, manifests, segments, and wal that restores without aliasing the live collection.

### Why this mechanism is necessary

Portable backups need a self-consistent cut of metadata, manifests, segments, and wal that restores without aliasing the live collection. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

a snapshot contains one declared generation and restore either publishes the whole verified copy or leaves the destination unchanged.

### Mechanism blocks

<!-- journey-file: src/miniqdrant/collection.py -->
<!-- journey-file: src/miniqdrant/database.py -->
<!-- journey-file: src/miniqdrant/persistence/snapshot.py -->
#### Atomic snapshot and restore mechanism

##### What it is and why it appears

The central mechanism is atomic snapshot and restore. Portable backups need a self-consistent cut of metadata, manifests, segments, and wal that restores without aliasing the live collection.

##### Runtime role

a snapshot contains one declared generation and restore either publishes the whole verified copy or leaves the destination unchanged.

##### Statement understanding

The durable boundary is this: a snapshot contains one declared generation and restore either publishes the whole verified copy or leaves the destination unchanged.



### Verification evidence

Run `uv run pytest -q $(cat journey/stages/13-snapshot-restore/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: a snapshot contains one declared generation and restore either publishes the whole verified copy or leaves the destination unchanged.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 10](https://github.com/system-in-miniature/mini-qdrant/blob/main/docs/tutorial/10-snapshots-methodology.md)

## 中文

### 目标

实现原子 Snapshot 与 Restore，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `src/miniqdrant/collection.py`
- `src/miniqdrant/database.py`
- `src/miniqdrant/persistence/snapshot.py`
- `tests/acceptance/test_snapshot_roundtrip.py`
- `tests/reliability/test_snapshot.py`
- `tests/reliability/test_snapshot_restore_failure.py`

### 当前遇到的问题

可移植备份需要 Metadata、Manifest、Segment 与 WAL 的自洽切面，恢复后不能与在线 Collection 共享身份。

### 测试契约

#### 先看会坏在哪里

聚焦测试让原子 Snapshot 与 Restore经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

<!-- journey-file: tests/acceptance/test_snapshot_roundtrip.py -->
<!-- journey-file: tests/reliability/test_snapshot.py -->
<!-- journey-file: tests/reliability/test_snapshot_restore_failure.py -->
#### 原子 Snapshot 与 Restore测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

聚焦测试让原子 Snapshot 与 Restore经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

##### 关键测试语句

```python
assert [hit.id for hit in restored.search(SearchRequest((1.0, 0.0, 0.0), 2)).hits] == [
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是原子 Snapshot 与 Restore。可移植备份需要 Metadata、Manifest、Segment 与 WAL 的自洽切面，恢复后不能与在线 Collection 共享身份。

### 为什么需要这个机制

可移植备份需要 Metadata、Manifest、Segment 与 WAL 的自洽切面，恢复后不能与在线 Collection 共享身份。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

Snapshot 只包含一个声明的 Generation，Restore 要么发布完整校验副本，要么保持目标不变。

### 机制板块

<!-- journey-file: src/miniqdrant/collection.py -->
<!-- journey-file: src/miniqdrant/database.py -->
<!-- journey-file: src/miniqdrant/persistence/snapshot.py -->
#### 原子 Snapshot 与 Restore机制

##### 是什么，为什么现在需要

核心机制是原子 Snapshot 与 Restore。可移植备份需要 Metadata、Manifest、Segment 与 WAL 的自洽切面，恢复后不能与在线 Collection 共享身份。

##### 在运行时做什么

Snapshot 只包含一个声明的 Generation，Restore 要么发布完整校验副本，要么保持目标不变。

##### 关键语句理解

真正要守住的边界是：Snapshot 只包含一个声明的 Generation，Restore 要么发布完整校验副本，要么保持目标不变。



### 验证证据

运行 `uv run pytest -q $(cat journey/stages/13-snapshot-restore/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：Snapshot 只包含一个声明的 Generation，Restore 要么发布完整校验副本，要么保持目标不变。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 10 章](https://github.com/system-in-miniature/mini-qdrant/blob/main/docs/zh/tutorial/10-snapshots-methodology.md)
