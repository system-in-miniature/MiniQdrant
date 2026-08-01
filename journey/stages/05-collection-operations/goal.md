# Stage 05 · Collection operations / Collection 操作闭环

<!-- journey: chapter=2 tests_added=2 -->

## English

### Goal

Build collection operations and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `src/miniqdrant/__init__.py`
- `src/miniqdrant/collection.py`
- `src/miniqdrant/database.py`
- `src/miniqdrant/lifecycle.py`
- `tests/acceptance/test_exact_collection.py`
- `tests/contract/test_collection.py`

### The problem at this point

Segments and indexes do not yet form a public database until one collection owns lifecycle, validation, upsert, delete, retrieve, and search.

### Test contract

#### See the failure first

The focused tests force collection operations through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

<!-- journey-file: tests/acceptance/test_exact_collection.py -->
<!-- journey-file: tests/contract/test_collection.py -->
#### Collection operations test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The focused tests force collection operations through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

##### Key test statement

```python
assert [hit.id for hit in result.hits] == [1, 3]
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is collection operations. Segments and indexes do not yet form a public database until one collection owns lifecycle, validation, upsert, delete, retrieve, and search.

### Why this mechanism is necessary

Segments and indexes do not yet form a public database until one collection owns lifecycle, validation, upsert, delete, retrieve, and search. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

public mutations validate completely before publication and reads never expose caller-owned mutable payload state.

### Mechanism blocks

<!-- journey-file: src/miniqdrant/collection.py -->
<!-- journey-file: src/miniqdrant/database.py -->
<!-- journey-file: src/miniqdrant/lifecycle.py -->
#### Collection operations mechanism

##### What it is and why it appears

The central mechanism is collection operations. Segments and indexes do not yet form a public database until one collection owns lifecycle, validation, upsert, delete, retrieve, and search.

##### Runtime role

public mutations validate completely before publication and reads never expose caller-owned mutable payload state.

##### Statement understanding

The durable boundary is this: public mutations validate completely before publication and reads never expose caller-owned mutable payload state.

<!-- journey-file: src/miniqdrant/__init__.py -->
#### Package, fixture, and project support

These files only keep exports, test corpora, dependencies, and the runtime environment reproducible; they are supporting wiring rather than vector-database mechanism logic.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/05-collection-operations/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: public mutations validate completely before publication and reads never expose caller-owned mutable payload state.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 2](https://github.com/system-in-miniature/mini-qdrant/blob/main/docs/tutorial/02-points-payload.md)

## 中文

### 目标

实现Collection 操作闭环，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `src/miniqdrant/__init__.py`
- `src/miniqdrant/collection.py`
- `src/miniqdrant/database.py`
- `src/miniqdrant/lifecycle.py`
- `tests/acceptance/test_exact_collection.py`
- `tests/contract/test_collection.py`

### 当前遇到的问题

Segment 与 Index 只有由一个 Collection 统一拥有生命周期、校验、Upsert、Delete、Retrieve 与 Search 后才构成公共数据库。

### 测试契约

#### 先看会坏在哪里

聚焦测试让Collection 操作闭环经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

<!-- journey-file: tests/acceptance/test_exact_collection.py -->
<!-- journey-file: tests/contract/test_collection.py -->
#### Collection 操作闭环测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

聚焦测试让Collection 操作闭环经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

##### 关键测试语句

```python
assert [hit.id for hit in result.hits] == [1, 3]
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是Collection 操作闭环。Segment 与 Index 只有由一个 Collection 统一拥有生命周期、校验、Upsert、Delete、Retrieve 与 Search 后才构成公共数据库。

### 为什么需要这个机制

Segment 与 Index 只有由一个 Collection 统一拥有生命周期、校验、Upsert、Delete、Retrieve 与 Search 后才构成公共数据库。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

公共修改在发布前完成全部校验，读取绝不暴露调用方可变 Payload 状态。

### 机制板块

<!-- journey-file: src/miniqdrant/collection.py -->
<!-- journey-file: src/miniqdrant/database.py -->
<!-- journey-file: src/miniqdrant/lifecycle.py -->
#### Collection 操作闭环机制

##### 是什么，为什么现在需要

核心机制是Collection 操作闭环。Segment 与 Index 只有由一个 Collection 统一拥有生命周期、校验、Upsert、Delete、Retrieve 与 Search 后才构成公共数据库。

##### 在运行时做什么

公共修改在发布前完成全部校验，读取绝不暴露调用方可变 Payload 状态。

##### 关键语句理解

真正要守住的边界是：公共修改在发布前完成全部校验，读取绝不暴露调用方可变 Payload 状态。

<!-- journey-file: src/miniqdrant/__init__.py -->
#### 包、Fixture 与工程支撑

这些文件只保持包导出、测试语料、依赖与运行环境可复现，不把支撑接线误讲成向量数据库机制。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/05-collection-operations/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：公共修改在发布前完成全部校验，读取绝不暴露调用方可变 Payload 状态。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 2 章](https://github.com/system-in-miniature/mini-qdrant/blob/main/docs/zh/tutorial/02-points-payload.md)
