# Stage 03 · Structured payload filters / 结构化 Payload 过滤

<!-- journey: chapter=6 tests_added=1 -->

## English

### Goal

Build structured payload filters and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `src/miniqdrant/__init__.py`
- `src/miniqdrant/filters/__init__.py`
- `src/miniqdrant/filters/ast.py`
- `src/miniqdrant/filters/evaluate.py`
- `tests/contract/test_filters.py`

### The problem at this point

Payload conditions need an explicit recursive ast instead of accidental python truthiness and dictionary comparison.

### Test contract

#### See the failure first

The focused tests force structured payload filters through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

<!-- journey-file: tests/contract/test_filters.py -->
#### Structured payload filters test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The focused tests force structured payload filters through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

##### Key test statement

```python
assert matches_filter(1, payload, condition)
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is structured payload filters. Payload conditions need an explicit recursive ast instead of accidental python truthiness and dictionary comparison.

### Why this mechanism is necessary

Payload conditions need an explicit recursive ast instead of accidental python truthiness and dictionary comparison. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

every condition has declared missing-field and type behavior, and boolean composition remains deterministic.

### Mechanism blocks

<!-- journey-file: src/miniqdrant/filters/ast.py -->
<!-- journey-file: src/miniqdrant/filters/evaluate.py -->
#### Structured payload filters mechanism

##### What it is and why it appears

The central mechanism is structured payload filters. Payload conditions need an explicit recursive ast instead of accidental python truthiness and dictionary comparison.

##### Runtime role

every condition has declared missing-field and type behavior, and boolean composition remains deterministic.

##### Statement understanding

The durable boundary is this: every condition has declared missing-field and type behavior, and boolean composition remains deterministic.

<!-- journey-file: src/miniqdrant/__init__.py -->
<!-- journey-file: src/miniqdrant/filters/__init__.py -->
#### Package, fixture, and project support

These files only keep exports, test corpora, dependencies, and the runtime environment reproducible; they are supporting wiring rather than vector-database mechanism logic.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/03-payload-filters/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: every condition has declared missing-field and type behavior, and boolean composition remains deterministic.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 6](https://github.com/system-in-miniature/mini-qdrant/blob/main/docs/tutorial/06-filtering.md)

## 中文

### 目标

实现结构化 Payload 过滤，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `src/miniqdrant/__init__.py`
- `src/miniqdrant/filters/__init__.py`
- `src/miniqdrant/filters/ast.py`
- `src/miniqdrant/filters/evaluate.py`
- `tests/contract/test_filters.py`

### 当前遇到的问题

Payload 条件需要显式递归 AST，不能依赖偶然的 Python Truthiness 与字典比较。

### 测试契约

#### 先看会坏在哪里

聚焦测试让结构化 Payload 过滤经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

<!-- journey-file: tests/contract/test_filters.py -->
#### 结构化 Payload 过滤测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

聚焦测试让结构化 Payload 过滤经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

##### 关键测试语句

```python
assert matches_filter(1, payload, condition)
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是结构化 Payload 过滤。Payload 条件需要显式递归 AST，不能依赖偶然的 Python Truthiness 与字典比较。

### 为什么需要这个机制

Payload 条件需要显式递归 AST，不能依赖偶然的 Python Truthiness 与字典比较。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

每个 Condition 都明确缺失字段和类型行为，Boolean 组合保持确定。

### 机制板块

<!-- journey-file: src/miniqdrant/filters/ast.py -->
<!-- journey-file: src/miniqdrant/filters/evaluate.py -->
#### 结构化 Payload 过滤机制

##### 是什么，为什么现在需要

核心机制是结构化 Payload 过滤。Payload 条件需要显式递归 AST，不能依赖偶然的 Python Truthiness 与字典比较。

##### 在运行时做什么

每个 Condition 都明确缺失字段和类型行为，Boolean 组合保持确定。

##### 关键语句理解

真正要守住的边界是：每个 Condition 都明确缺失字段和类型行为，Boolean 组合保持确定。

<!-- journey-file: src/miniqdrant/__init__.py -->
<!-- journey-file: src/miniqdrant/filters/__init__.py -->
#### 包、Fixture 与工程支撑

这些文件只保持包导出、测试语料、依赖与运行环境可复现，不把支撑接线误讲成向量数据库机制。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/03-payload-filters/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：每个 Condition 都明确缺失字段和类型行为，Boolean 组合保持确定。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 6 章](https://github.com/system-in-miniature/mini-qdrant/blob/main/docs/zh/tutorial/06-filtering.md)
