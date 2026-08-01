# Stage 09 · Framed write-ahead logging / 分帧预写日志

<!-- journey: chapter=3 tests_added=3 -->

## English

### Goal

Build framed write-ahead logging and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `src/miniqdrant/persistence/__init__.py`
- `src/miniqdrant/persistence/frame.py`
- `src/miniqdrant/persistence/fsync.py`
- `src/miniqdrant/persistence/wal.py`
- `tests/reliability/test_wal_replay.py`
- `tests/reliability/test_wal_tail.py`
- `tests/storage/test_wal_codec.py`

### The problem at this point

Acknowledged operations need ordered, checksummed frames whose valid prefix is recoverable after truncation or tail corruption.

### Test contract

#### See the failure first

The focused tests force framed write-ahead logging through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

<!-- journey-file: tests/reliability/test_wal_replay.py -->
<!-- journey-file: tests/reliability/test_wal_tail.py -->
<!-- journey-file: tests/storage/test_wal_codec.py -->
#### Framed write-ahead logging test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The focused tests force framed write-ahead logging through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

##### Key test statement

```python
assert list(wal.replay(after_sequence=2)) == [third]
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is framed write-ahead logging. Acknowledged operations need ordered, checksummed frames whose valid prefix is recoverable after truncation or tail corruption.

### Why this mechanism is necessary

Acknowledged operations need ordered, checksummed frames whose valid prefix is recoverable after truncation or tail corruption. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

a mutation is publishable only after its complete frame is durable, and recovery never skips corruption to invent later history.

### Mechanism blocks

<!-- journey-file: src/miniqdrant/persistence/frame.py -->
<!-- journey-file: src/miniqdrant/persistence/fsync.py -->
<!-- journey-file: src/miniqdrant/persistence/wal.py -->
#### Framed write-ahead logging mechanism

##### What it is and why it appears

The central mechanism is framed write-ahead logging. Acknowledged operations need ordered, checksummed frames whose valid prefix is recoverable after truncation or tail corruption.

##### Runtime role

a mutation is publishable only after its complete frame is durable, and recovery never skips corruption to invent later history.

##### Statement understanding

The durable boundary is this: a mutation is publishable only after its complete frame is durable, and recovery never skips corruption to invent later history.

<!-- journey-file: src/miniqdrant/persistence/__init__.py -->
#### Package, fixture, and project support

These files only keep exports, test corpora, dependencies, and the runtime environment reproducible; they are supporting wiring rather than vector-database mechanism logic.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/09-framed-wal/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: a mutation is publishable only after its complete frame is durable, and recovery never skips corruption to invent later history.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 3](https://github.com/system-in-miniature/mini-qdrant/blob/main/docs/tutorial/03-wal-manifest.md)

## 中文

### 目标

实现分帧预写日志，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `src/miniqdrant/persistence/__init__.py`
- `src/miniqdrant/persistence/frame.py`
- `src/miniqdrant/persistence/fsync.py`
- `src/miniqdrant/persistence/wal.py`
- `tests/reliability/test_wal_replay.py`
- `tests/reliability/test_wal_tail.py`
- `tests/storage/test_wal_codec.py`

### 当前遇到的问题

已确认操作需要有序、带校验和的 Frame，使截断或尾部损坏后仍能恢复有效前缀。

### 测试契约

#### 先看会坏在哪里

聚焦测试让分帧预写日志经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

<!-- journey-file: tests/reliability/test_wal_replay.py -->
<!-- journey-file: tests/reliability/test_wal_tail.py -->
<!-- journey-file: tests/storage/test_wal_codec.py -->
#### 分帧预写日志测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

聚焦测试让分帧预写日志经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

##### 关键测试语句

```python
assert list(wal.replay(after_sequence=2)) == [third]
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是分帧预写日志。已确认操作需要有序、带校验和的 Frame，使截断或尾部损坏后仍能恢复有效前缀。

### 为什么需要这个机制

已确认操作需要有序、带校验和的 Frame，使截断或尾部损坏后仍能恢复有效前缀。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

Mutation 只有完整 Frame 持久后才能发布，恢复绝不跳过损坏去虚构后续历史。

### 机制板块

<!-- journey-file: src/miniqdrant/persistence/frame.py -->
<!-- journey-file: src/miniqdrant/persistence/fsync.py -->
<!-- journey-file: src/miniqdrant/persistence/wal.py -->
#### 分帧预写日志机制

##### 是什么，为什么现在需要

核心机制是分帧预写日志。已确认操作需要有序、带校验和的 Frame，使截断或尾部损坏后仍能恢复有效前缀。

##### 在运行时做什么

Mutation 只有完整 Frame 持久后才能发布，恢复绝不跳过损坏去虚构后续历史。

##### 关键语句理解

真正要守住的边界是：Mutation 只有完整 Frame 持久后才能发布，恢复绝不跳过损坏去虚构后续历史。

<!-- journey-file: src/miniqdrant/persistence/__init__.py -->
#### 包、Fixture 与工程支撑

这些文件只保持包导出、测试语料、依赖与运行环境可复现，不把支撑接线误讲成向量数据库机制。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/09-framed-wal/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：Mutation 只有完整 Frame 持久后才能发布，恢复绝不跳过损坏去虚构后续历史。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 3 章](https://github.com/system-in-miniature/mini-qdrant/blob/main/docs/zh/tutorial/03-wal-manifest.md)
