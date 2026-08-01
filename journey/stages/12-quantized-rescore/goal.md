# Stage 12 · Quantized candidate rescoring / 量化候选精排

<!-- journey: chapter=8 tests_added=2 -->

## English

### Goal

Build quantized candidate rescoring and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `src/miniqdrant/index/__init__.py`
- `src/miniqdrant/index/quantization.py`
- `src/miniqdrant/query/executor.py`
- `src/miniqdrant/segment/immutable.py`
- `tests/index/test_quantization.py`
- `tests/query/test_quantized_rescore.py`

### The problem at this point

Compressed vectors can accelerate candidate generation only if bounded approximation and exact final scoring are kept distinct.

### Test contract

#### See the failure first

The focused tests force quantized candidate rescoring through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

<!-- journey-file: tests/index/test_quantization.py -->
<!-- journey-file: tests/query/test_quantized_rescore.py -->
#### Quantized candidate rescoring test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The focused tests force quantized candidate rescoring through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

##### Key test statement

```python
assert self._quantized is not None
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is quantized candidate rescoring. Compressed vectors can accelerate candidate generation only if bounded approximation and exact final scoring are kept distinct.

### Why this mechanism is necessary

Compressed vectors can accelerate candidate generation only if bounded approximation and exact final scoring are kept distinct. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

quantization may change candidate cost but returned scores and ordering come from exact vectors after rescoring.

### Mechanism blocks

<!-- journey-file: src/miniqdrant/index/quantization.py -->
<!-- journey-file: src/miniqdrant/query/executor.py -->
<!-- journey-file: src/miniqdrant/segment/immutable.py -->
#### Quantized candidate rescoring mechanism

##### What it is and why it appears

The central mechanism is quantized candidate rescoring. Compressed vectors can accelerate candidate generation only if bounded approximation and exact final scoring are kept distinct.

##### Runtime role

quantization may change candidate cost but returned scores and ordering come from exact vectors after rescoring.

##### Statement understanding

The durable boundary is this: quantization may change candidate cost but returned scores and ordering come from exact vectors after rescoring.

<!-- journey-file: src/miniqdrant/index/__init__.py -->
#### Package, fixture, and project support

These files only keep exports, test corpora, dependencies, and the runtime environment reproducible; they are supporting wiring rather than vector-database mechanism logic.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/12-quantized-rescore/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: quantization may change candidate cost but returned scores and ordering come from exact vectors after rescoring.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 8](https://github.com/system-in-miniature/mini-qdrant/blob/main/docs/tutorial/08-quantization.md)

## 中文

### 目标

实现量化候选精排，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `src/miniqdrant/index/__init__.py`
- `src/miniqdrant/index/quantization.py`
- `src/miniqdrant/query/executor.py`
- `src/miniqdrant/segment/immutable.py`
- `tests/index/test_quantization.py`
- `tests/query/test_quantized_rescore.py`

### 当前遇到的问题

压缩 Vector 只有在区分有界近似 Candidate Generation 与最终精确评分时才能安全加速。

### 测试契约

#### 先看会坏在哪里

聚焦测试让量化候选精排经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

<!-- journey-file: tests/index/test_quantization.py -->
<!-- journey-file: tests/query/test_quantized_rescore.py -->
#### 量化候选精排测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

聚焦测试让量化候选精排经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

##### 关键测试语句

```python
assert self._quantized is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是量化候选精排。压缩 Vector 只有在区分有界近似 Candidate Generation 与最终精确评分时才能安全加速。

### 为什么需要这个机制

压缩 Vector 只有在区分有界近似 Candidate Generation 与最终精确评分时才能安全加速。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

Quantization 可以改变候选成本，但返回分数与顺序来自精确 Vector 的再次评分。

### 机制板块

<!-- journey-file: src/miniqdrant/index/quantization.py -->
<!-- journey-file: src/miniqdrant/query/executor.py -->
<!-- journey-file: src/miniqdrant/segment/immutable.py -->
#### 量化候选精排机制

##### 是什么，为什么现在需要

核心机制是量化候选精排。压缩 Vector 只有在区分有界近似 Candidate Generation 与最终精确评分时才能安全加速。

##### 在运行时做什么

Quantization 可以改变候选成本，但返回分数与顺序来自精确 Vector 的再次评分。

##### 关键语句理解

真正要守住的边界是：Quantization 可以改变候选成本，但返回分数与顺序来自精确 Vector 的再次评分。

<!-- journey-file: src/miniqdrant/index/__init__.py -->
#### 包、Fixture 与工程支撑

这些文件只保持包导出、测试语料、依赖与运行环境可复现，不把支撑接线误讲成向量数据库机制。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/12-quantized-rescore/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：Quantization 可以改变候选成本，但返回分数与顺序来自精确 Vector 的再次评分。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 8 章](https://github.com/system-in-miniature/mini-qdrant/blob/main/docs/zh/tutorial/08-quantization.md)
