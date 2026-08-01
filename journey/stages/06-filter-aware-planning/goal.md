# Stage 06 · Filter-aware query planning / 过滤感知查询规划

<!-- journey: chapter=7 tests_added=3 -->

## English

### Goal

Build filter-aware query planning and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `src/miniqdrant/__init__.py`
- `src/miniqdrant/collection.py`
- `src/miniqdrant/filters/__init__.py`
- `src/miniqdrant/filters/cardinality.py`
- `src/miniqdrant/filters/index.py`
- `src/miniqdrant/query/__init__.py`
- `src/miniqdrant/query/executor.py`
- `src/miniqdrant/query/planner.py`
- `src/miniqdrant/segment/mutable.py`
- `tests/query/test_payload_index.py`
- `tests/query/test_plan_parity.py`
- `tests/query/test_planner.py`

### The problem at this point

Exact scans, payload indexes, and filters need a planner that can choose candidates without changing result semantics.

### Test contract

#### See the failure first

The focused tests force filter-aware query planning through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

<!-- journey-file: tests/query/test_payload_index.py -->
<!-- journey-file: tests/query/test_plan_parity.py -->
<!-- journey-file: tests/query/test_planner.py -->
#### Filter-aware query planning test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The focused tests force filter-aware query planning through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

##### Key test statement

```python
assert identifiers is not None
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is filter-aware query planning. Exact scans, payload indexes, and filters need a planner that can choose candidates without changing result semantics.

### Why this mechanism is necessary

Exact scans, payload indexes, and filters need a planner that can choose candidates without changing result semantics. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

plans may narrow candidates but execution always preserves filter and exact-score parity with the reference scan.

### Mechanism blocks

<!-- journey-file: src/miniqdrant/collection.py -->
<!-- journey-file: src/miniqdrant/filters/cardinality.py -->
<!-- journey-file: src/miniqdrant/filters/index.py -->
<!-- journey-file: src/miniqdrant/query/executor.py -->
<!-- journey-file: src/miniqdrant/query/planner.py -->
<!-- journey-file: src/miniqdrant/segment/mutable.py -->
#### Filter-aware query planning mechanism

##### What it is and why it appears

The central mechanism is filter-aware query planning. Exact scans, payload indexes, and filters need a planner that can choose candidates without changing result semantics.

##### Runtime role

plans may narrow candidates but execution always preserves filter and exact-score parity with the reference scan.

##### Statement understanding

The durable boundary is this: plans may narrow candidates but execution always preserves filter and exact-score parity with the reference scan.

<!-- journey-file: src/miniqdrant/__init__.py -->
<!-- journey-file: src/miniqdrant/filters/__init__.py -->
<!-- journey-file: src/miniqdrant/query/__init__.py -->
#### Package, fixture, and project support

These files only keep exports, test corpora, dependencies, and the runtime environment reproducible; they are supporting wiring rather than vector-database mechanism logic.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/06-filter-aware-planning/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: plans may narrow candidates but execution always preserves filter and exact-score parity with the reference scan.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 7](https://github.com/system-in-miniature/mini-qdrant/blob/main/docs/tutorial/07-planner.md)

## 中文

### 目标

实现过滤感知查询规划，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `src/miniqdrant/__init__.py`
- `src/miniqdrant/collection.py`
- `src/miniqdrant/filters/__init__.py`
- `src/miniqdrant/filters/cardinality.py`
- `src/miniqdrant/filters/index.py`
- `src/miniqdrant/query/__init__.py`
- `src/miniqdrant/query/executor.py`
- `src/miniqdrant/query/planner.py`
- `src/miniqdrant/segment/mutable.py`
- `tests/query/test_payload_index.py`
- `tests/query/test_plan_parity.py`
- `tests/query/test_planner.py`

### 当前遇到的问题

精确扫描、Payload Index 与 Filter 需要 Planner 选择 Candidate，同时不得改变结果语义。

### 测试契约

#### 先看会坏在哪里

聚焦测试让过滤感知查询规划经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

<!-- journey-file: tests/query/test_payload_index.py -->
<!-- journey-file: tests/query/test_plan_parity.py -->
<!-- journey-file: tests/query/test_planner.py -->
#### 过滤感知查询规划测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

聚焦测试让过滤感知查询规划经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

##### 关键测试语句

```python
assert identifiers is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是过滤感知查询规划。精确扫描、Payload Index 与 Filter 需要 Planner 选择 Candidate，同时不得改变结果语义。

### 为什么需要这个机制

精确扫描、Payload Index 与 Filter 需要 Planner 选择 Candidate，同时不得改变结果语义。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

Plan 可以缩小 Candidate，但执行始终保持与参考扫描相同的 Filter 和精确分数语义。

### 机制板块

<!-- journey-file: src/miniqdrant/collection.py -->
<!-- journey-file: src/miniqdrant/filters/cardinality.py -->
<!-- journey-file: src/miniqdrant/filters/index.py -->
<!-- journey-file: src/miniqdrant/query/executor.py -->
<!-- journey-file: src/miniqdrant/query/planner.py -->
<!-- journey-file: src/miniqdrant/segment/mutable.py -->
#### 过滤感知查询规划机制

##### 是什么，为什么现在需要

核心机制是过滤感知查询规划。精确扫描、Payload Index 与 Filter 需要 Planner 选择 Candidate，同时不得改变结果语义。

##### 在运行时做什么

Plan 可以缩小 Candidate，但执行始终保持与参考扫描相同的 Filter 和精确分数语义。

##### 关键语句理解

真正要守住的边界是：Plan 可以缩小 Candidate，但执行始终保持与参考扫描相同的 Filter 和精确分数语义。

<!-- journey-file: src/miniqdrant/__init__.py -->
<!-- journey-file: src/miniqdrant/filters/__init__.py -->
<!-- journey-file: src/miniqdrant/query/__init__.py -->
#### 包、Fixture 与工程支撑

这些文件只保持包导出、测试语料、依赖与运行环境可复现，不把支撑接线误讲成向量数据库机制。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/06-filter-aware-planning/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：Plan 可以缩小 Candidate，但执行始终保持与参考扫描相同的 Filter 和精确分数语义。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 7 章](https://github.com/system-in-miniature/mini-qdrant/blob/main/docs/zh/tutorial/07-planner.md)
