# 第 7 章：查询规划

> [English](../../tutorial/07-planner.md) · 中文

向量索引并不自动等于最佳执行路径。小段直接扫描可能更便宜；高选择性的索引过滤可能把工作缩到少量精确打分；大型无过滤段才值得使用 HNSW。MiniQdrant 用一个五策略规划器把这个决定公开出来，并通过 `SearchResult.plan` 返回所选策略。

## 学习目标

完成本章后，你应当能够：

1. 说出五个 `Strategy` 值及各自选择条件；
2. 解释规划器为何使用过滤估计的上界；
3. 跟踪公开 `SearchRequest` 如何为每个段产生一项计划；
4. 解读 `SearchResult.plan` 与 `visited_count`，又不夸大性能；
5. 指出 MiniQdrant 固定规划器与真实 Qdrant 的差异。

## 1. 规划事实，而不是点数据

`src/miniqdrant/query/planner.py` 包含三个小数据类型。`SegmentFacts` 描述决策输入：live 点总数、可选 `CardinalityEstimate`、HNSW 与量化是否可用，以及精确搜索覆盖开关。`SearchPlan` 记录所选 `Strategy`、人类可读的原因、总数和估计。`QueryPlanner` 拥有两个非负阈值。

规划器不打分向量，也不求值 payload。这种拆分让行为具有确定性，且可直接单元测试。`QueryPlanner.choose()` 的有序决策树是：

1. `exact_requested` → `EXACT_FULL_SCAN`；
2. 小段或没有 HNSW → `EXACT_FULL_SCAN`；
3. 过滤上界不超过过滤阈值 → `FILTER_THEN_EXACT`；
4. 有量化 → `QUANTIZED_HNSW_RESCORE`；
5. 剩余情况中有过滤 → `FILTERED_HNSW`；
6. 否则 → `HNSW`。

顺序本身就是策略。精确请求压过所有索引；小段即使同时有 HNSW 与量化也保持 plain；高选择性过滤先于量化；大型段一旦到达第 4 步，量化会压过有过滤和无过滤图策略。

准确的策略名 `QUANTIZED_HNSW_RESCORE` 带有历史暗示，但运行行为会误导人：当前分支从不调用 HNSW。第 8 章将检查这个缺口。

## 2. 为什么安全输入是基数上界

第 6 章介绍了 `CardinalityEstimate(minimum, expected, maximum, exact)`。`QueryPlanner.choose()` 把 `filtered.maximum` 与精确扫描阈值比较，而不是用 `expected`。

假设未解析过滤留下 120 个候选，并产生教学估计 `[0, 60, 120]`。阈值 100 时，不能因为期望值 60 就安全选择 filter-then-exact：residual 可能放行全部 120 个点。使用上界确保所选精确路径受配置的最坏情况限制。这是一种保守规划。

当前 `src/miniqdrant/filters/index.py::PayloadIndexSet.candidates` 中的估计器有意保持粗糙。精确索引结果的三个边界相等；非精确结果用零、保守候选集的一半和完整大小。规划器教授的是估计如何流入决策，而不是生产直方图如何构建。

## 3. 从 `SearchRequest` 到逐段计划

`src/miniqdrant/collection.py::Collection.search` 捕获稳定的 `CollectionView`，其 `search()` 调用模块级 `src/miniqdrant/collection.py::_search`。该函数校验请求，并让每个非空 immutable/mutable 快照独立搜索。

在 `src/miniqdrant/segment/immutable.py::ImmutableSegment.search` 内：

1. 校验查询向量，并归一化 cosine 查询；
2. `PayloadIndexSet.candidates()` 提供 ID 与基数估计；
3. 构造 `QueryPlanner`；
4. 用 `SegmentFacts` 描述当前段；
5. 执行所选分支；
6. 把计划标签写入 `SegmentSearchResult.strategy`。

collection 使用全局 `TopK` 合并逐段结果，拒绝陈旧版本和 tombstone，应用 score threshold，然后返回：

```python
SearchResult(
    hits,
    plan=tuple(result.strategy for result in segment_results),
)
```

因此，计划可观察性是逐段的。有三个已发布段的 collection 可能返回三个标签。这不是一个全局代价计划，也不会暴露算子树。

阈值还有一个源码级细节：`ImmutableSegment.search()` 把 `config.optimizer.indexing_threshold_points` 同时传给 `plain_threshold` 与 `filter_scan_threshold`。虽然 `QueryPlanner.__init__()` 接受两个旋钮，运行时目前把它们折叠成一个配置值。

### 无歧义地读取决策树

调试时，应把事实写在分支顺序旁边，而不是从计划标签直接跳到结论。某段可能拥有 HNSW，却因低于 plain 阈值选择 `EXACT_FULL_SCAN`；量化段可能因过滤上界很小而选择 `FILTER_THEN_EXACT`；反过来，无索引过滤可能保留很大的保守上界，把段送到 `FILTERED_HNSW`。这些结果都不能证明“索引缺失”。

`SearchPlan` 的 reason 字符串就是为这种检查准备的。先读 `plan.reason`，再核对 `total_points`、`filtered.maximum`、`has_hnsw`、`has_quantization`、`exact_requested`。若事实错误，故障位于规划器之前，通常是候选估计或段构建；若事实正确但策略不理想，应修改并测试 `QueryPlanner.choose()`，而不是把特例藏进 executor；若计划正确但结果错误，则跟踪 `ImmutableSegment.search()` 中对应分支。这种“事实构建—策略选择—执行”的三分法，避免性能策略讨论掩盖结果正确性 bug。

### 计划稳定性与配置变化

确定性 planner 让配置实验可以复现。给定相同 `SegmentFacts` 和阈值，`choose()` 总会返回相同 plan 与 reason；决策中没有隐藏 timing sample、cache state 或后台统计刷新。这非常适合教学系统，但也意味着配置变化会产生明显悬崖：阈值为 100 时，段从 100 增长到 101 个点，就可能从 exact scan 切到 HNSW，尽管 workload 只变化了一点。

应把阈值调优视为需要 result parity 和 measured work 验证的假设，而不是正确性变更。因为 HNSW 与量化有 recall trade-off，精确和近似分支可能返回不同 ID；但 filter、版本可见性、score threshold 与确定性 tie rule 仍必须成立。持久化变化后的配置时，还要记住 `src/miniqdrant/config.py::config_fingerprint` 参与 collection 与 segment schema 检查。MiniQdrant 不支持 online schema migration，因此就地修改配置不是让既有 collection 重新规划的受支持捷径。

## 4. `visited_count` 到底表示什么

每种段策略都会返回 `visited_count`，但它是分支特定的工作计数器：

- 精确与量化扫描统计被打分的合格向量；
- HNSW 统计访问过的唯一图节点；
- filtered HNSW 统计图工作量，而不只是最终接纳点数。

公开 `SearchResult` 暴露计划标签，却不暴露该计数。lab 直接调用段搜索进行比较。即便如此，这些计数也不是可直接比较的 CPU 成本：一次图访问、一次解码浮点量化打分和一次精确打分的工作不同。

更重要的是，`src/miniqdrant/collection.py::Collection.capture_view` 会扫描段记录，重建最新记录映射；`src/miniqdrant/collection.py::_stale_live_count` 又扫描每个段，以便在拒绝陈旧版本后仍请求到足够候选。因此，低 HNSW visit 数并不会让 MiniQdrant 端到端搜索变成次线性。[`DIFFERENCES_FROM_QDRANT.md`](https://github.com/system-in-miniature/mini-qdrant/blob/main/DIFFERENCES_FROM_QDRANT.md) 第 3 条明确声明了这一点。

## 5. 与真实 Qdrant 对照

真实 Qdrant 同样进行逐段查询优化。它的段查询优化与基数估计代码位于 `lib/segment/src/index/query_optimization/` 以及结构化 payload 索引一带。生产规划会考虑更丰富的字段索引、索引配置、段状态、过滤结构、适合硬件的阈值和 filter-aware 图机制。

MiniQdrant 保留了有用的架构形状：收集段事实、估计选择性、选择策略、执行并暴露证据。它刻意简化或反转了若干细节：

- 只有五个固定分支；
- 阈值是点数，运行时还为两类决策复用一个阈值；
- 非精确基数采用中点启发式；
- filtered HNSW 是后过滤，不是 filter-aware 遍历；
- 量化计划是全扫描，不使用 HNSW；
- `SearchResult.plan` 是教学观测工具，不兼容 Qdrant telemetry 或 explain API。

参见[行为矩阵](../behavior-matrix.md)的基数规划行、[完整差异文档](https://github.com/system-in-miniature/mini-qdrant/blob/main/DIFFERENCES_FROM_QDRANT.md)第 1、2、3、7、10 条，以及 [Qdrant 映射](../qdrant-mapping.md)中的 `QueryPlanner`、`Strategy.FILTERED_HNSW` 和 labs 行。

## 6. 动手实验

### 实验 A：比较四条可观察执行路径

```bash
UV_CACHE_DIR=/tmp/miniqdrant-uv-cache uv run python -m miniqdrant.labs.plan_comparison
```

实测输出：

```text
Same query: vector=(1.0, 0.0), limit=5
`visited_count` is the plan-specific work counter: scored eligible vectors or unique graph nodes.
    exact | plan=exact_full_scan          | visited= 64 | ids=(0, 1, 63, 2, 62)
     hnsw | plan=hnsw                     | visited= 33 | ids=(0, 1, 63, 2, 62)
 filtered | plan=filtered_hnsw            | visited= 36 | ids=(0, 2, 62, 4, 60)
quantized | plan=quantized_hnsw_rescore   | visited= 64 | ids=(0, 1, 63, 2, 62)

Interpretation:
- exact visits every eligible vector; HNSW follows the graph.
- filtered-HNSW traverses first and filters an oversampled candidate set.
- the quantized plan scans decoded int8 codes, then float-rescores candidates.
- plan names describe planner branches; see DIFFERENCES_FROM_QDRANT.md.
```

量化路径访问全部 64 个点是关键观察：标签只能证明走了哪个分支，不能证明生产算法运行过或性能提升。

### 实验 B：验证每个规划边界

```bash
UV_CACHE_DIR=/tmp/miniqdrant-uv-cache uv run pytest -q tests/query/test_planner.py tests/query/test_plan_parity.py
```

实测输出：

```text
........                                                                 [100%]
8 passed in 0.25s
```

`tests/query/test_planner.py::test_planner_boundaries` 提供小段、高选择性过滤、大过滤、HNSW、量化和强制精确六类事实。`test_plan_is_inspectable` 检查 reason 字符串；parity 测试检查围绕索引做规划不会改变精确结果。

## 7. 练习

1. **理解题：**阈值为 100 时，一个 10,000 点 HNSW 段的过滤估计为 `[0, 40, 80]`，选择什么策略？
2. **理解题：**为什么一次搜索中的两个段可以合理报告不同策略？
3. **动手策略题：**在 scratch diff 中新增独立的 `filter_scan_threshold_points` 配置字段，并把它接入 `ImmutableSegment.search()`。不要修改仓库 `src/`。验收标准：展示一个 plain 阈值为 10、filter 阈值为 100 的单元测试，并给出精确运行命令。

??? note "参考答案"

    1. `FILTER_THEN_EXACT`。段先绕过小段分支，而保守上界 80 不超过 100。
    2. 规划按 immutable/mutable 段进行。段大小、索引是否存在、量化和过滤估计都可能不同；`_search()` 最后把它们的候选合并到全局 Top-K。
    3. scratch diff 应向 `OptimizerConfig` 增加正整数配置；通过 `asdict` 自动保留序列化；将它作为 `filter_scan_threshold`，同时让 `indexing_threshold_points` 继续作为 `plain_threshold`。聚焦测试应断言：50 个无过滤点是否扫描只由 plain 规则决定，而估计上界 50 会在独立 filter 规则下选择 `FILTER_THEN_EXACT`。验收命令：`UV_CACHE_DIR=/tmp/miniqdrant-uv-cache uv run pytest -q tests/query/test_planner.py tests/query/test_hnsw_plans.py`。

## 小结

MiniQdrant 规划器刻意小到可以直接读成有序决策树。它消费保守的段事实，把正确性置于乐观估计之前，为每个段选择五条分支之一，并返回计划标签供检查。标签必须结合真实 executor 解读。第 8 章将针对标量量化这样做：看清 int8 表示、近似候选、精确重打分，以及带 HNSW 的误导性名字如何彼此分离。
