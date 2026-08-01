# Stage 01 · Domain contracts / 领域契约

<!-- journey: chapter=2 tests_added=2 -->

## English

### Goal

Build domain contracts and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `pyproject.toml`
- `src/miniqdrant/__init__.py`
- `src/miniqdrant/config.py`
- `src/miniqdrant/errors.py`
- `src/miniqdrant/ids.py`
- `src/miniqdrant/json_values.py`
- `src/miniqdrant/models.py`
- `tests/test_project_contract.py`
- `tests/unit/test_domain.py`
- `uv.lock`

### The problem at this point

Points, vectors, payload values, ids, distance modes, and collection configuration need closed validation before storage or search can reason about them.

### Test contract

#### See the failure first

The focused tests force domain contracts through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

<!-- journey-file: tests/test_project_contract.py -->
<!-- journey-file: tests/unit/test_domain.py -->
#### Domain contracts test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The focused tests force domain contracts through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

##### Key test statement

```python
assert isinstance(frozen, Mapping)
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is domain contracts. Points, vectors, payload values, ids, distance modes, and collection configuration need closed validation before storage or search can reason about them.

### Why this mechanism is necessary

Points, vectors, payload values, ids, distance modes, and collection configuration need closed validation before storage or search can reason about them. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

accepted values are owned and canonical, dimensions remain fixed, and unsupported types fail at the public boundary.

### Mechanism blocks

<!-- journey-file: src/miniqdrant/config.py -->
<!-- journey-file: src/miniqdrant/errors.py -->
<!-- journey-file: src/miniqdrant/ids.py -->
<!-- journey-file: src/miniqdrant/json_values.py -->
<!-- journey-file: src/miniqdrant/models.py -->
#### Domain contracts mechanism

##### What it is and why it appears

The central mechanism is domain contracts. Points, vectors, payload values, ids, distance modes, and collection configuration need closed validation before storage or search can reason about them.

##### Runtime role

accepted values are owned and canonical, dimensions remain fixed, and unsupported types fail at the public boundary.

##### Statement understanding

The durable boundary is this: accepted values are owned and canonical, dimensions remain fixed, and unsupported types fail at the public boundary.

<!-- journey-file: pyproject.toml -->
<!-- journey-file: src/miniqdrant/__init__.py -->
<!-- journey-file: uv.lock -->
#### Package, fixture, and project support

These files only keep exports, test corpora, dependencies, and the runtime environment reproducible; they are supporting wiring rather than vector-database mechanism logic.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/01-domain-contracts/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: accepted values are owned and canonical, dimensions remain fixed, and unsupported types fail at the public boundary.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 2](https://github.com/system-in-miniature/mini-qdrant/blob/main/docs/tutorial/02-points-payload.md)

## 中文

### 目标

实现领域契约，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `pyproject.toml`
- `src/miniqdrant/__init__.py`
- `src/miniqdrant/config.py`
- `src/miniqdrant/errors.py`
- `src/miniqdrant/ids.py`
- `src/miniqdrant/json_values.py`
- `src/miniqdrant/models.py`
- `tests/test_project_contract.py`
- `tests/unit/test_domain.py`
- `uv.lock`

### 当前遇到的问题

Point、Vector、Payload Value、ID、Distance Mode 与 Collection Configuration 必须先形成封闭校验，存储和搜索才能可靠推理。

### 测试契约

#### 先看会坏在哪里

聚焦测试让领域契约经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

<!-- journey-file: tests/test_project_contract.py -->
<!-- journey-file: tests/unit/test_domain.py -->
#### 领域契约测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

聚焦测试让领域契约经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

##### 关键测试语句

```python
assert isinstance(frozen, Mapping)
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是领域契约。Point、Vector、Payload Value、ID、Distance Mode 与 Collection Configuration 必须先形成封闭校验，存储和搜索才能可靠推理。

### 为什么需要这个机制

Point、Vector、Payload Value、ID、Distance Mode 与 Collection Configuration 必须先形成封闭校验，存储和搜索才能可靠推理。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

被接受的值由系统拥有且具有规范表示，维度保持固定，不支持的类型在公共边界失败。

### 机制板块

<!-- journey-file: src/miniqdrant/config.py -->
<!-- journey-file: src/miniqdrant/errors.py -->
<!-- journey-file: src/miniqdrant/ids.py -->
<!-- journey-file: src/miniqdrant/json_values.py -->
<!-- journey-file: src/miniqdrant/models.py -->
#### 领域契约机制

##### 是什么，为什么现在需要

核心机制是领域契约。Point、Vector、Payload Value、ID、Distance Mode 与 Collection Configuration 必须先形成封闭校验，存储和搜索才能可靠推理。

##### 在运行时做什么

被接受的值由系统拥有且具有规范表示，维度保持固定，不支持的类型在公共边界失败。

##### 关键语句理解

真正要守住的边界是：被接受的值由系统拥有且具有规范表示，维度保持固定，不支持的类型在公共边界失败。

<!-- journey-file: pyproject.toml -->
<!-- journey-file: src/miniqdrant/__init__.py -->
<!-- journey-file: uv.lock -->
#### 包、Fixture 与工程支撑

这些文件只保持包导出、测试语料、依赖与运行环境可复现，不把支撑接线误讲成向量数据库机制。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/01-domain-contracts/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：被接受的值由系统拥有且具有规范表示，维度保持固定，不支持的类型在公共边界失败。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 2 章](https://github.com/system-in-miniature/mini-qdrant/blob/main/docs/zh/tutorial/02-points-payload.md)
