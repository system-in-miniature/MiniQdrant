# Stage 15 · Executable vector-search labs / 可执行向量搜索实验

<!-- journey: chapter=10 tests_added=1 -->

## English

### Goal

Build executable vector-search labs and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `pyproject.toml`
- `src/miniqdrant/index/hnsw.py`
- `src/miniqdrant/labs/filtering.py`
- `src/miniqdrant/labs/plan_comparison.py`
- `src/miniqdrant/labs/recall.py`
- `src/miniqdrant/labs/recovery.py`
- `src/miniqdrant/labs/segments.py`
- `src/miniqdrant/persistence/frame.py`
- `src/miniqdrant/persistence/manifest.py`
- `src/miniqdrant/persistence/wal.py`
- `tests/acceptance/test_labs.py`

### The problem at this point

Isolated contracts do not show whether learners can reproduce filtering, recall, recovery, segments, and plan choice through public apis.

### Test contract

#### See the failure first

The focused tests force executable vector-search labs through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

<!-- journey-file: tests/acceptance/test_labs.py -->
#### Executable vector-search labs test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The focused tests force executable vector-search labs through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

##### Key test statement

```python
assert expected_output in completed.stdout.lower()
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is executable vector-search labs. Isolated contracts do not show whether learners can reproduce filtering, recall, recovery, segments, and plan choice through public apis.

### Why this mechanism is necessary

Isolated contracts do not show whether learners can reproduce filtering, recall, recovery, segments, and plan choice through public apis. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

each fresh-process lab exposes one mechanism through stable observable output without private fixtures or pre-existing state.

### Mechanism blocks

<!-- journey-file: src/miniqdrant/index/hnsw.py -->
<!-- journey-file: src/miniqdrant/labs/filtering.py -->
<!-- journey-file: src/miniqdrant/labs/plan_comparison.py -->
<!-- journey-file: src/miniqdrant/labs/recall.py -->
<!-- journey-file: src/miniqdrant/labs/recovery.py -->
<!-- journey-file: src/miniqdrant/labs/segments.py -->
<!-- journey-file: src/miniqdrant/persistence/frame.py -->
<!-- journey-file: src/miniqdrant/persistence/manifest.py -->
<!-- journey-file: src/miniqdrant/persistence/wal.py -->
#### Executable vector-search labs mechanism

##### What it is and why it appears

The central mechanism is executable vector-search labs. Isolated contracts do not show whether learners can reproduce filtering, recall, recovery, segments, and plan choice through public apis.

##### Runtime role

each fresh-process lab exposes one mechanism through stable observable output without private fixtures or pre-existing state.

##### Statement understanding

The durable boundary is this: each fresh-process lab exposes one mechanism through stable observable output without private fixtures or pre-existing state.

<!-- journey-file: pyproject.toml -->
#### Package, fixture, and project support

These files only keep exports, test corpora, dependencies, and the runtime environment reproducible; they are supporting wiring rather than vector-database mechanism logic.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/15-executable-labs/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: each fresh-process lab exposes one mechanism through stable observable output without private fixtures or pre-existing state.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 10](https://github.com/system-in-miniature/mini-qdrant/blob/main/docs/tutorial/10-snapshots-methodology.md)

## 中文

### 目标

实现可执行向量搜索实验，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `pyproject.toml`
- `src/miniqdrant/index/hnsw.py`
- `src/miniqdrant/labs/filtering.py`
- `src/miniqdrant/labs/plan_comparison.py`
- `src/miniqdrant/labs/recall.py`
- `src/miniqdrant/labs/recovery.py`
- `src/miniqdrant/labs/segments.py`
- `src/miniqdrant/persistence/frame.py`
- `src/miniqdrant/persistence/manifest.py`
- `src/miniqdrant/persistence/wal.py`
- `tests/acceptance/test_labs.py`

### 当前遇到的问题

孤立契约无法说明学习者能否仅通过公共 API 复现 Filtering、Recall、Recovery、Segment 与 Plan Choice。

### 测试契约

#### 先看会坏在哪里

聚焦测试让可执行向量搜索实验经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

<!-- journey-file: tests/acceptance/test_labs.py -->
#### 可执行向量搜索实验测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

聚焦测试让可执行向量搜索实验经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

##### 关键测试语句

```python
assert expected_output in completed.stdout.lower()
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是可执行向量搜索实验。孤立契约无法说明学习者能否仅通过公共 API 复现 Filtering、Recall、Recovery、Segment 与 Plan Choice。

### 为什么需要这个机制

孤立契约无法说明学习者能否仅通过公共 API 复现 Filtering、Recall、Recovery、Segment 与 Plan Choice。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

每个新进程 Lab 都通过稳定可观察输出展示一个机制，不依赖私有 Fixture 或既有状态。

### 机制板块

<!-- journey-file: src/miniqdrant/index/hnsw.py -->
<!-- journey-file: src/miniqdrant/labs/filtering.py -->
<!-- journey-file: src/miniqdrant/labs/plan_comparison.py -->
<!-- journey-file: src/miniqdrant/labs/recall.py -->
<!-- journey-file: src/miniqdrant/labs/recovery.py -->
<!-- journey-file: src/miniqdrant/labs/segments.py -->
<!-- journey-file: src/miniqdrant/persistence/frame.py -->
<!-- journey-file: src/miniqdrant/persistence/manifest.py -->
<!-- journey-file: src/miniqdrant/persistence/wal.py -->
#### 可执行向量搜索实验机制

##### 是什么，为什么现在需要

核心机制是可执行向量搜索实验。孤立契约无法说明学习者能否仅通过公共 API 复现 Filtering、Recall、Recovery、Segment 与 Plan Choice。

##### 在运行时做什么

每个新进程 Lab 都通过稳定可观察输出展示一个机制，不依赖私有 Fixture 或既有状态。

##### 关键语句理解

真正要守住的边界是：每个新进程 Lab 都通过稳定可观察输出展示一个机制，不依赖私有 Fixture 或既有状态。

<!-- journey-file: pyproject.toml -->
#### 包、Fixture 与工程支撑

这些文件只保持包导出、测试语料、依赖与运行环境可复现，不把支撑接线误讲成向量数据库机制。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/15-executable-labs/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：每个新进程 Lab 都通过稳定可观察输出展示一个机制，不依赖私有 Fixture 或既有状态。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 10 章](https://github.com/system-in-miniature/mini-qdrant/blob/main/docs/zh/tutorial/10-snapshots-methodology.md)
