# Stage 02 · Distance scoring and top-k / 距离评分与 Top-k

<!-- journey: chapter=2 tests_added=2 -->

## English

### Goal

Build distance scoring and top-k and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `src/miniqdrant/__init__.py`
- `src/miniqdrant/metrics.py`
- `src/miniqdrant/topk.py`
- `tests/unit/test_metrics.py`
- `tests/unit/test_topk.py`

### The problem at this point

Exact search needs one deterministic meaning for cosine, dot, euclidean distance, ties, limits, and non-finite components.

### Test contract

#### See the failure first

The focused tests force distance scoring and top-k through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

<!-- journey-file: tests/unit/test_metrics.py -->
<!-- journey-file: tests/unit/test_topk.py -->
#### Distance scoring and top-k test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The focused tests force distance scoring and top-k through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

##### Key test statement

```python
assert score(Distance.DOT, (1.0, 2.0), (3.0, 4.0)) == pytest.approx(11.0)
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is distance scoring and top-k. Exact search needs one deterministic meaning for cosine, dot, euclidean distance, ties, limits, and non-finite components.

### Why this mechanism is necessary

Exact search needs one deterministic meaning for cosine, dot, euclidean distance, ties, limits, and non-finite components. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

all metrics expose a common higher-is-better score and top-k ordering is stable under equal scores.

### Mechanism blocks

<!-- journey-file: src/miniqdrant/metrics.py -->
<!-- journey-file: src/miniqdrant/topk.py -->
#### Distance scoring and top-k mechanism

##### What it is and why it appears

The central mechanism is distance scoring and top-k. Exact search needs one deterministic meaning for cosine, dot, euclidean distance, ties, limits, and non-finite components.

##### Runtime role

all metrics expose a common higher-is-better score and top-k ordering is stable under equal scores.

##### Statement understanding

The durable boundary is this: all metrics expose a common higher-is-better score and top-k ordering is stable under equal scores.

<!-- journey-file: src/miniqdrant/__init__.py -->
#### Package, fixture, and project support

These files only keep exports, test corpora, dependencies, and the runtime environment reproducible; they are supporting wiring rather than vector-database mechanism logic.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/02-distance-topk/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: all metrics expose a common higher-is-better score and top-k ordering is stable under equal scores.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 2](https://github.com/system-in-miniature/mini-qdrant/blob/main/docs/tutorial/02-points-payload.md)

## 中文

### 目标

实现距离评分与 Top-k，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `src/miniqdrant/__init__.py`
- `src/miniqdrant/metrics.py`
- `src/miniqdrant/topk.py`
- `tests/unit/test_metrics.py`
- `tests/unit/test_topk.py`

### 当前遇到的问题

精确搜索需要统一定义 Cosine、Dot、Euclidean Distance、Tie、Limit 与非有限分量。

### 测试契约

#### 先看会坏在哪里

聚焦测试让距离评分与 Top-k经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

<!-- journey-file: tests/unit/test_metrics.py -->
<!-- journey-file: tests/unit/test_topk.py -->
#### 距离评分与 Top-k测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

聚焦测试让距离评分与 Top-k经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

##### 关键测试语句

```python
assert score(Distance.DOT, (1.0, 2.0), (3.0, 4.0)) == pytest.approx(11.0)
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是距离评分与 Top-k。精确搜索需要统一定义 Cosine、Dot、Euclidean Distance、Tie、Limit 与非有限分量。

### 为什么需要这个机制

精确搜索需要统一定义 Cosine、Dot、Euclidean Distance、Tie、Limit 与非有限分量。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

所有 Metric 暴露统一的分数越高越好语义，相同分数下 Top-k 顺序保持稳定。

### 机制板块

<!-- journey-file: src/miniqdrant/metrics.py -->
<!-- journey-file: src/miniqdrant/topk.py -->
#### 距离评分与 Top-k机制

##### 是什么，为什么现在需要

核心机制是距离评分与 Top-k。精确搜索需要统一定义 Cosine、Dot、Euclidean Distance、Tie、Limit 与非有限分量。

##### 在运行时做什么

所有 Metric 暴露统一的分数越高越好语义，相同分数下 Top-k 顺序保持稳定。

##### 关键语句理解

真正要守住的边界是：所有 Metric 暴露统一的分数越高越好语义，相同分数下 Top-k 顺序保持稳定。

<!-- journey-file: src/miniqdrant/__init__.py -->
#### 包、Fixture 与工程支撑

这些文件只保持包导出、测试语料、依赖与运行环境可复现，不把支撑接线误讲成向量数据库机制。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/02-distance-topk/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：所有 Metric 暴露统一的分数越高越好语义，相同分数下 Top-k 顺序保持稳定。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 2 章](https://github.com/system-in-miniature/mini-qdrant/blob/main/docs/zh/tutorial/02-points-payload.md)
