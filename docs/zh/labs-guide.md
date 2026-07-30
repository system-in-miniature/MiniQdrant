# 动手实验

> [English](../labs-guide.md) · 中文版

先在仓库根目录安装：

```bash
uv sync
```

所有 lab 都是确定性的；需要持久化时会使用临时目录。

## 1. 载荷过滤

```bash
uv run python -m miniqdrant.labs.filtering
```

预期输出 `Matching ids: [1, 3]` 以及所选计划。点 `2` 在向量上相似，但属于
租户 `b`，因此被排除。重点观察公开 Collection API 如何组合向量评分与载荷
索引候选集。

## 2. 不可变分段与优化

```bash
uv run python -m miniqdrant.labs.segments
```

预期：

```text
Segments before optimize: 2
Segments after optimize: 1
```

每轮 upsert + flush 发布一个不可变分段；`optimize()` 将两个已发布分段压缩成
一个，同时保持集合内容不变。

## 3. 关闭与重启恢复

```bash
uv run python -m miniqdrant.labs.recovery
```

预期输出 `Restored ids: [1, 2]`。实验执行 flush、close，再打开新的
`Database`，迫使元数据与分段状态经过公开生命周期边界完成恢复。

## 4. 比较四种搜索计划

```bash
uv run python -m miniqdrant.labs.plan_comparison
```

预期计划标签为 `exact_full_scan`、`hnsw`、`filtered_hnsw` 和
`quantized_hnsw_rescore`，并各自带 `visited_count`。比较工作量与命中 ID，
但同时阅读[与 Qdrant 的差异](DIFFERENCES_FROM_QDRANT.md)：量化分支虽有教学
计划名，实际是解码 int8 后全扫并用 float 重评分。

## 5. HNSW 召回率

```bash
uv run python -m miniqdrant.labs.recall
```

固定种子会在 80 个点上运行 5 个查询并打印平均 `recall@5`（当前夹具为
`1.000`）。精确搜索提供参考集合，指标统计精确 top-5 ID 有多少也出现在
HNSW 候选中。这是可复现实验，不是生产基准测试。

可按[行为矩阵](behavior-matrix.md)继续运行聚焦测试，或用
`uv run pytest -q` 运行全部测试。
