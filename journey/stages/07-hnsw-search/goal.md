# Stage 07 · Deterministic HNSW search / 确定性 HNSW 搜索

<!-- journey: chapter=5 tests_added=3 -->

## English

### Goal

Build deterministic hnsw search and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `src/miniqdrant/index/__init__.py`
- `src/miniqdrant/index/hnsw.py`
- `tests/index/test_hnsw_graph.py`
- `tests/index/test_hnsw_recall.py`
- `tests/index/test_hnsw_search.py`

### The problem at this point

Approximate nearest-neighbor retrieval needs explicit graph layers, neighbor bounds, entry points, traversal budgets, and tie rules.

### Test contract

#### See the failure first

The focused tests force deterministic hnsw search through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

<!-- journey-file: tests/index/test_hnsw_graph.py -->
<!-- journey-file: tests/index/test_hnsw_recall.py -->
<!-- journey-file: tests/index/test_hnsw_search.py -->
#### Deterministic HNSW search test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The focused tests force deterministic hnsw search through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

##### Key test statement

```python
assert first.export_graph() == second.export_graph()
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is deterministic hnsw search. Approximate nearest-neighbor retrieval needs explicit graph layers, neighbor bounds, entry points, traversal budgets, and tie rules.

### Why this mechanism is necessary

Approximate nearest-neighbor retrieval needs explicit graph layers, neighbor bounds, entry points, traversal budgets, and tie rules. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

graph construction and search are reproducible and never return deleted, duplicate, or out-of-scope candidates.

### Mechanism blocks

<!-- journey-file: src/miniqdrant/index/hnsw.py -->
#### Deterministic HNSW search mechanism

##### What it is and why it appears

The central mechanism is deterministic hnsw search. Approximate nearest-neighbor retrieval needs explicit graph layers, neighbor bounds, entry points, traversal budgets, and tie rules.

##### Runtime role

graph construction and search are reproducible and never return deleted, duplicate, or out-of-scope candidates.

##### Statement understanding

The durable boundary is this: graph construction and search are reproducible and never return deleted, duplicate, or out-of-scope candidates.

<!-- journey-file: src/miniqdrant/index/__init__.py -->
#### Package, fixture, and project support

These files only keep exports, test corpora, dependencies, and the runtime environment reproducible; they are supporting wiring rather than vector-database mechanism logic.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/07-hnsw-search/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: graph construction and search are reproducible and never return deleted, duplicate, or out-of-scope candidates.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 5](https://github.com/system-in-miniature/mini-qdrant/blob/main/docs/tutorial/05-hnsw.md)

## 中文

### 目标

实现确定性 HNSW 搜索，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `src/miniqdrant/index/__init__.py`
- `src/miniqdrant/index/hnsw.py`
- `tests/index/test_hnsw_graph.py`
- `tests/index/test_hnsw_recall.py`
- `tests/index/test_hnsw_search.py`

### 当前遇到的问题

近似最近邻检索需要显式 Graph Layer、Neighbor Bound、Entry Point、Traversal Budget 与 Tie Rule。

### 测试契约

#### 先看会坏在哪里

聚焦测试让确定性 HNSW 搜索经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

<!-- journey-file: tests/index/test_hnsw_graph.py -->
<!-- journey-file: tests/index/test_hnsw_recall.py -->
<!-- journey-file: tests/index/test_hnsw_search.py -->
#### 确定性 HNSW 搜索测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

聚焦测试让确定性 HNSW 搜索经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

##### 关键测试语句

```python
assert first.export_graph() == second.export_graph()
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是确定性 HNSW 搜索。近似最近邻检索需要显式 Graph Layer、Neighbor Bound、Entry Point、Traversal Budget 与 Tie Rule。

### 为什么需要这个机制

近似最近邻检索需要显式 Graph Layer、Neighbor Bound、Entry Point、Traversal Budget 与 Tie Rule。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

Graph 构建与搜索可复现，绝不返回已删除、重复或越界 Candidate。

### 机制板块

<!-- journey-file: src/miniqdrant/index/hnsw.py -->
#### 确定性 HNSW 搜索机制

##### 是什么，为什么现在需要

核心机制是确定性 HNSW 搜索。近似最近邻检索需要显式 Graph Layer、Neighbor Bound、Entry Point、Traversal Budget 与 Tie Rule。

##### 在运行时做什么

Graph 构建与搜索可复现，绝不返回已删除、重复或越界 Candidate。

##### 关键语句理解

真正要守住的边界是：Graph 构建与搜索可复现，绝不返回已删除、重复或越界 Candidate。

<!-- journey-file: src/miniqdrant/index/__init__.py -->
#### 包、Fixture 与工程支撑

这些文件只保持包导出、测试语料、依赖与运行环境可复现，不把支撑接线误讲成向量数据库机制。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/07-hnsw-search/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：Graph 构建与搜索可复现，绝不返回已删除、重复或越界 Candidate。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 5 章](https://github.com/system-in-miniature/mini-qdrant/blob/main/docs/zh/tutorial/05-hnsw.md)
