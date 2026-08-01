# Stage 04 · Exact mutable segments / 精确可变 Segment

<!-- journey: chapter=4 tests_added=2 -->

## English

### Goal

Build exact mutable segments and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `src/miniqdrant/__init__.py`
- `src/miniqdrant/index/__init__.py`
- `src/miniqdrant/index/plain.py`
- `src/miniqdrant/segment/__init__.py`
- `src/miniqdrant/segment/base.py`
- `src/miniqdrant/segment/mutable.py`
- `tests/contract/test_mutable_segment.py`
- `tests/index/test_plain.py`

### The problem at this point

New points need an owned in-memory segment that coordinates replacement, deletion, filtering, and exact vector retrieval.

### Test contract

#### See the failure first

The focused tests force exact mutable segments through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

<!-- journey-file: tests/contract/test_mutable_segment.py -->
<!-- journey-file: tests/index/test_plain.py -->
#### Exact mutable segments test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The focused tests force exact mutable segments through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

##### Key test statement

```python
assert [(hit.point_id, hit.version) for hit in hits.candidates] == [(1, 1)]
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is exact mutable segments. New points need an owned in-memory segment that coordinates replacement, deletion, filtering, and exact vector retrieval.

### Why this mechanism is necessary

New points need an owned in-memory segment that coordinates replacement, deletion, filtering, and exact vector retrieval. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

a point id has at most one live record and every search result is rederived from the segment's current owned state.

### Mechanism blocks

<!-- journey-file: src/miniqdrant/index/plain.py -->
<!-- journey-file: src/miniqdrant/segment/base.py -->
<!-- journey-file: src/miniqdrant/segment/mutable.py -->
#### Exact mutable segments mechanism

##### What it is and why it appears

The central mechanism is exact mutable segments. New points need an owned in-memory segment that coordinates replacement, deletion, filtering, and exact vector retrieval.

##### Runtime role

a point id has at most one live record and every search result is rederived from the segment's current owned state.

##### Statement understanding

The durable boundary is this: a point id has at most one live record and every search result is rederived from the segment's current owned state.

<!-- journey-file: src/miniqdrant/__init__.py -->
<!-- journey-file: src/miniqdrant/index/__init__.py -->
<!-- journey-file: src/miniqdrant/segment/__init__.py -->
#### Package, fixture, and project support

These files only keep exports, test corpora, dependencies, and the runtime environment reproducible; they are supporting wiring rather than vector-database mechanism logic.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/04-mutable-segment/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: a point id has at most one live record and every search result is rederived from the segment's current owned state.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 4](https://github.com/system-in-miniature/mini-qdrant/blob/main/docs/tutorial/04-segments.md)

## 中文

### 目标

实现精确可变 Segment，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `src/miniqdrant/__init__.py`
- `src/miniqdrant/index/__init__.py`
- `src/miniqdrant/index/plain.py`
- `src/miniqdrant/segment/__init__.py`
- `src/miniqdrant/segment/base.py`
- `src/miniqdrant/segment/mutable.py`
- `tests/contract/test_mutable_segment.py`
- `tests/index/test_plain.py`

### 当前遇到的问题

新 Point 需要受控的内存 Segment，统一协调替换、删除、过滤与精确向量检索。

### 测试契约

#### 先看会坏在哪里

聚焦测试让精确可变 Segment经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

<!-- journey-file: tests/contract/test_mutable_segment.py -->
<!-- journey-file: tests/index/test_plain.py -->
#### 精确可变 Segment测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

聚焦测试让精确可变 Segment经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

##### 关键测试语句

```python
assert [(hit.point_id, hit.version) for hit in hits.candidates] == [(1, 1)]
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是精确可变 Segment。新 Point 需要受控的内存 Segment，统一协调替换、删除、过滤与精确向量检索。

### 为什么需要这个机制

新 Point 需要受控的内存 Segment，统一协调替换、删除、过滤与精确向量检索。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

一个 Point ID 至多对应一条活记录，每个搜索结果都从 Segment 当前受控状态重新推导。

### 机制板块

<!-- journey-file: src/miniqdrant/index/plain.py -->
<!-- journey-file: src/miniqdrant/segment/base.py -->
<!-- journey-file: src/miniqdrant/segment/mutable.py -->
#### 精确可变 Segment机制

##### 是什么，为什么现在需要

核心机制是精确可变 Segment。新 Point 需要受控的内存 Segment，统一协调替换、删除、过滤与精确向量检索。

##### 在运行时做什么

一个 Point ID 至多对应一条活记录，每个搜索结果都从 Segment 当前受控状态重新推导。

##### 关键语句理解

真正要守住的边界是：一个 Point ID 至多对应一条活记录，每个搜索结果都从 Segment 当前受控状态重新推导。

<!-- journey-file: src/miniqdrant/__init__.py -->
<!-- journey-file: src/miniqdrant/index/__init__.py -->
<!-- journey-file: src/miniqdrant/segment/__init__.py -->
#### 包、Fixture 与工程支撑

这些文件只保持包导出、测试语料、依赖与运行环境可复现，不把支撑接线误讲成向量数据库机制。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/04-mutable-segment/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：一个 Point ID 至多对应一条活记录，每个搜索结果都从 Segment 当前受控状态重新推导。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 4 章](https://github.com/system-in-miniature/mini-qdrant/blob/main/docs/zh/tutorial/04-segments.md)
