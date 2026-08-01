# Stage 14 · Concurrency and acceptance closure / 并发与验收闭环

<!-- journey: chapter=9 tests_added=9 -->

## English

### Goal

Build concurrency and acceptance closure and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `src/miniqdrant/cli.py`
- `src/miniqdrant/collection.py`
- `src/miniqdrant/labs/__init__.py`
- `src/miniqdrant/labs/filtering.py`
- `src/miniqdrant/labs/recall.py`
- `src/miniqdrant/labs/recovery.py`
- `src/miniqdrant/labs/segments.py`
- `src/miniqdrant/persistence/manifest.py`
- `tests/acceptance/test_cli.py`
- `tests/acceptance/test_cross_segment_search.py`
- `tests/acceptance/test_final_acceptance.py`
- `tests/acceptance/test_labs.py`
- `tests/concurrency/test_online_optimize.py`
- `tests/contract/test_collection.py`
- `tests/contract/test_lifecycle.py`
- `tests/storage/test_manifest.py`
- `tests/test_sloc_report.py`

### The problem at this point

Flush and optimize can race, while cross-segment merge can surface the same point id more than once unless lifecycle ownership is tightened.

### Test contract

#### See the failure first

The focused tests force concurrency and acceptance closure through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

<!-- journey-file: tests/acceptance/test_cli.py -->
<!-- journey-file: tests/acceptance/test_cross_segment_search.py -->
<!-- journey-file: tests/acceptance/test_final_acceptance.py -->
<!-- journey-file: tests/acceptance/test_labs.py -->
<!-- journey-file: tests/concurrency/test_online_optimize.py -->
<!-- journey-file: tests/contract/test_collection.py -->
<!-- journey-file: tests/contract/test_lifecycle.py -->
<!-- journey-file: tests/storage/test_manifest.py -->
<!-- journey-file: tests/test_sloc_report.py -->
#### Concurrency and acceptance closure test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The focused tests force concurrency and acceptance closure through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

##### Key test statement

```python
assert json.loads(upsert.stdout)["accepted"] == 2
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is concurrency and acceptance closure. Flush and optimize can race, while cross-segment merge can surface the same point id more than once unless lifecycle ownership is tightened.

### Why this mechanism is necessary

Flush and optimize can race, while cross-segment merge can surface the same point id more than once unless lifecycle ownership is tightened. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

lifecycle mutations serialize at publication and merged search emits only the newest live identity for each point.

### Mechanism blocks

<!-- journey-file: src/miniqdrant/cli.py -->
<!-- journey-file: src/miniqdrant/collection.py -->
<!-- journey-file: src/miniqdrant/labs/filtering.py -->
<!-- journey-file: src/miniqdrant/labs/recall.py -->
<!-- journey-file: src/miniqdrant/labs/recovery.py -->
<!-- journey-file: src/miniqdrant/labs/segments.py -->
<!-- journey-file: src/miniqdrant/persistence/manifest.py -->
#### Concurrency and acceptance closure mechanism

##### What it is and why it appears

The central mechanism is concurrency and acceptance closure. Flush and optimize can race, while cross-segment merge can surface the same point id more than once unless lifecycle ownership is tightened.

##### Runtime role

lifecycle mutations serialize at publication and merged search emits only the newest live identity for each point.

##### Statement understanding

The durable boundary is this: lifecycle mutations serialize at publication and merged search emits only the newest live identity for each point.

<!-- journey-file: src/miniqdrant/labs/__init__.py -->
#### Package, fixture, and project support

These files only keep exports, test corpora, dependencies, and the runtime environment reproducible; they are supporting wiring rather than vector-database mechanism logic.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/14-concurrency-acceptance/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: lifecycle mutations serialize at publication and merged search emits only the newest live identity for each point.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 9](https://github.com/system-in-miniature/mini-qdrant/blob/main/docs/tutorial/09-optimizer.md)

## 中文

### 目标

实现并发与验收闭环，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `src/miniqdrant/cli.py`
- `src/miniqdrant/collection.py`
- `src/miniqdrant/labs/__init__.py`
- `src/miniqdrant/labs/filtering.py`
- `src/miniqdrant/labs/recall.py`
- `src/miniqdrant/labs/recovery.py`
- `src/miniqdrant/labs/segments.py`
- `src/miniqdrant/persistence/manifest.py`
- `tests/acceptance/test_cli.py`
- `tests/acceptance/test_cross_segment_search.py`
- `tests/acceptance/test_final_acceptance.py`
- `tests/acceptance/test_labs.py`
- `tests/concurrency/test_online_optimize.py`
- `tests/contract/test_collection.py`
- `tests/contract/test_lifecycle.py`
- `tests/storage/test_manifest.py`
- `tests/test_sloc_report.py`

### 当前遇到的问题

Flush 与 Optimize 可能竞争，跨 Segment Merge 也可能重复暴露同一 Point ID，必须收紧生命周期所有权。

### 测试契约

#### 先看会坏在哪里

聚焦测试让并发与验收闭环经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

<!-- journey-file: tests/acceptance/test_cli.py -->
<!-- journey-file: tests/acceptance/test_cross_segment_search.py -->
<!-- journey-file: tests/acceptance/test_final_acceptance.py -->
<!-- journey-file: tests/acceptance/test_labs.py -->
<!-- journey-file: tests/concurrency/test_online_optimize.py -->
<!-- journey-file: tests/contract/test_collection.py -->
<!-- journey-file: tests/contract/test_lifecycle.py -->
<!-- journey-file: tests/storage/test_manifest.py -->
<!-- journey-file: tests/test_sloc_report.py -->
#### 并发与验收闭环测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

聚焦测试让并发与验收闭环经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

##### 关键测试语句

```python
assert json.loads(upsert.stdout)["accepted"] == 2
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是并发与验收闭环。Flush 与 Optimize 可能竞争，跨 Segment Merge 也可能重复暴露同一 Point ID，必须收紧生命周期所有权。

### 为什么需要这个机制

Flush 与 Optimize 可能竞争，跨 Segment Merge 也可能重复暴露同一 Point ID，必须收紧生命周期所有权。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

生命周期修改在发布点串行化，合并搜索对每个 Point 只输出最新活身份。

### 机制板块

<!-- journey-file: src/miniqdrant/cli.py -->
<!-- journey-file: src/miniqdrant/collection.py -->
<!-- journey-file: src/miniqdrant/labs/filtering.py -->
<!-- journey-file: src/miniqdrant/labs/recall.py -->
<!-- journey-file: src/miniqdrant/labs/recovery.py -->
<!-- journey-file: src/miniqdrant/labs/segments.py -->
<!-- journey-file: src/miniqdrant/persistence/manifest.py -->
#### 并发与验收闭环机制

##### 是什么，为什么现在需要

核心机制是并发与验收闭环。Flush 与 Optimize 可能竞争，跨 Segment Merge 也可能重复暴露同一 Point ID，必须收紧生命周期所有权。

##### 在运行时做什么

生命周期修改在发布点串行化，合并搜索对每个 Point 只输出最新活身份。

##### 关键语句理解

真正要守住的边界是：生命周期修改在发布点串行化，合并搜索对每个 Point 只输出最新活身份。

<!-- journey-file: src/miniqdrant/labs/__init__.py -->
#### 包、Fixture 与工程支撑

这些文件只保持包导出、测试语料、依赖与运行环境可复现，不把支撑接线误讲成向量数据库机制。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/14-concurrency-acceptance/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：生命周期修改在发布点串行化，合并搜索对每个 Point 只输出最新活身份。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 9 章](https://github.com/system-in-miniature/mini-qdrant/blob/main/docs/zh/tutorial/09-optimizer.md)
