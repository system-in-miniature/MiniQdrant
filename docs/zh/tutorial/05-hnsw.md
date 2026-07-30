# 第 5 章 · HNSW

精确搜索为每个合格向量打分，简单且权威，但工作量随 segment 大小线性增长。
Hierarchical Navigable Small World（HNSW）用保证穷举换取一张尽快到达强候选的图。
MiniQdrant 保留可辨认的 HNSW 形状，同时让构建确定且可检查。

## 学习目标

学完本章后，你能够：

1. 解释 level、layer、entry point、degree bound 与 `ef` breadth；
2. 追踪插入的上层下降、邻居搜索和 prune；
3. 追踪查询从 greedy descent 到 layer-zero convergence；
4. 解读 `visited_count` 而不把它误当延迟保证；
5. 诚实说明 MiniQdrant 非标准 restart/pruning 差异。

## 分层邻近图

`src/miniqdrant/index/hnsw.py::HnswIndex` 保存 vector、version、每个 ID 的 level、每层
adjacency map、deleted ID、entry point 与 max level。Layer 0 包含所有点；更高层逐渐
稀疏，作为长距离路由捷径。查询先下降稀疏上层，再探索稠密底层。

生产 HNSW 通常随机采样 level。MiniQdrant 的 `hnsw.py::_deterministic_level` 把
point ID 与 `HnswConfig.seed` 一起 hash，再统计低位连续 1（最高 16）。这种类几何
分布跨运行和插入顺序稳定，支持可复现 graph/test，但不表示 Qdrant 分配相同 level。

`src/miniqdrant/config.py` 的 `HnswConfig` 暴露：

- `m`：每节点每层最多保留邻居数；
- `ef_construct`：插入选邻居时的搜索宽度；
- `ef_search`：默认 layer-zero 搜索宽度；
- `seed`：确定性 level seed。

`__post_init__` 要求正 `m`、`ef_construct >= m` 与正 `ef_search`。这是结构 guard，
不是生产调参建议。

需要把 construction breadth 与 query breadth 分开思考。`ef_construct` 在塑造连接
时一次性花费工作；弱 graph 不一定能靠昂贵查询完全修复。`ef_search` 为每次请求
花费工作，不改变已存 adjacency。二者都与 `m`、数据几何、filter 和 restart 行为
交互，所以一个 fixture 的调参不能给出通用值；应针对实际数据，以 exact search
为基准测 recall，并报告 visited work。

## 构建：导航、连接、裁剪

`HnswIndex.__init__` 先按规范 ID 排序 point，再调用 `_insert`。第一个点成为 entry
point。后续每个点由 `_insert` 计算 level，并为所占每层创建空 adjacency set。

若当前 graph 有高于新点 level 的层，插入从顶向下调用 `_greedy`。它反复移动到
分数更好的邻居；平分时 `_better` 用稳定 point-ID 顺序。此阶段只导航，不连新点。

在每个共享层，`_search_layer` 从当前 entry 以 `ef_construct` 宽度探索。按高分再
按 ID 排序的最佳候选成为至多 `m` 个邻居，双向加边；随后对新点和受影响邻居执行
`_prune`，确保 retained adjacency 不超过 `m`。

MiniQdrant pruning 保留 `m` 个最近邻，并为丢弃连接移除反向边。生产 HNSW 常用
diversity-aware heuristic：稍远邻居可能提供通往不同区域的更好路线。仅最近裁剪
更短、更确定，却可能产生断连或较难导航的 cluster。这是质量与可检查性的显式权衡。

若新点 level 高于旧最大值，它成为新 entry point 并提高 `_max_level`。导出的
`HnswGraph` 冻结 entry、levels 和已排序 adjacency list，让 codec/实验无需修改图
即可检查。

## 搜索：下降、收敛、收集

`HnswIndex.search` 校验正 limit 和查询维度，并归一化 cosine query。Breadth 是
`max(limit, ef_search or config.ef_search)`，必须至少保留足够候选满足 limit。

从全局 entry point 开始，搜索对 `max_level` 到 1 调用 `_greedy`。一层找到的最佳
点成为下一更稠密层的 entry。Layer 0 上，`_search_layer` 做 best-first expansion。

`_search_layer` 维护：

- `visited`，每节点至多处理一次；
- `scores`，避免重复打分；
- best-first `frontier`；以及
- 当前 `ef` 大小的 `best` 收敛窗口。

弹出 frontier candidate 后，方法排序 best window。若窗口已满且下一 frontier
score 比窗口最差成员还差，在本实现顺序下队列不可能改善集合，因此停止；否则为
未访问邻居打分，只有留在 best window 的才进入 frontier。

最后 `TopK` 排除 mark-deleted node 和 `allowed_ids` 外 ID，返回带存储版本的
candidate。Collection 搜索随后做 latest-version 与 residual-filter 检查。因此
HNSW candidate 不自动等于可见结果。

## 非标准穷举 restart

仅最近、有限度 graph 可能断连。标准 HNSW 从 entry point 出发，不枚举每个断连
分量。MiniQdrant 在 `HnswIndex.search` 增加显式循环：若已评分候选少于 breadth
且仍有未访问 vector，就选择最小 ID 的未访问点并搜索该分量。

Restart 让微型教学 graph 更易检查、recall 测试不易抖动，但它不标准。分量很小或
`ef` 很大时，循环可反复 restart 并访问所有 vector，把“近似”搜索变成全扫描。
小 fixture 的高 recall 可能测到 fallback，而不是良好 navigability。

限制已写在 module docstring、
[`HnswIndex` 映射](../qdrant-mapping.md#查询与索引)、
[`确定性 HNSW`](../behavior-matrix.md#行为矩阵)条目和
[与 Qdrant 的差异](https://github.com/system-in-miniature/mini-qdrant/blob/main/DIFFERENCES_FROM_QDRANT.md#其他有意简化)中。任何 benchmark
解读都不能隐藏它。

## Segment 如何选择 HNSW

只有 `indexed=True` 且 segment 有 live point 时才构建 HNSW。
`src/miniqdrant/segment/immutable.py::ImmutableSegment.search` 创建 `SegmentFacts`
并让 `QueryPlanner.choose` 选策略。Exact request 或小/plain 条件仍可能全扫描；
有 HNSW 的 segment 可根据 facts/config 选择 `hnsw` 或过滤路线。

Graph search 在有 filter 时可能先请求超过最终 limit 的候选，再 residual filtering。
MiniQdrant 的 `FILTERED_HNSW` 名字不能当成 Qdrant parity：它没有真正 filter-aware
graph navigation，而是 oversample 后 post-filter。Qdrant 把 filtering 融入 graph
traversal 以避免 recall/latency 问题，映射表因此标为“语义相反”。

`SearchResult.plan` 暴露策略。低层 HNSW/lab 暴露 `visited_count`，但 collection
结果当前只报告 plan，不汇总访问数。固定 fixture 的访问数是确定性工作证据，不是
latency、throughput、native memory 或生产 benchmark。

## 持久化提醒

`SegmentImage` 可把 `HnswGraph` 编码到 `hnsw.bin`，codec 读取时也会校验。然而
`SegmentImage.to_segment` 新建 `ImmutableSegment`，会从 live point 重建 HNSW，
而非安装解码图。确定性 rebuild 给出一致教学索引，但缺少存图的生产理由——快速
复用。映射表刻意把该路径标为“语义相反”。

所以成功 reopen 证明语义重建与校验，不证明快速 index loading；不能只因存在
`hnsw.bin` 就推断启动性能。

## MiniQdrant 对照真实 Qdrant

真实 Qdrant HNSW 用优化系统代码实现，并集成 segment storage、filter-aware
traversal、quantization、后台 indexing、生产 heuristic 和 telemetry。MiniQdrant
用 Python object、确定性 level/tie-breaking、nearest-only pruning 与穷举 component
restart，且 open 时重建图。

可迁移机制仍然丰富：稀疏上层做长距离导航，layer 0 精化候选，`ef` 控制有限
search/construction window，degree pruning 控制图大小，近似 candidate generation
与最终 visibility 分离。具体 heuristic 与性能不可迁移。

## 动手实验：检查确定性 graph

```bash
export UV_CACHE_DIR=/tmp/miniqdrant-uv-cache
uv run python - <<'PY'
from miniqdrant.config import (
    CollectionConfig, Distance, HnswConfig
)
from miniqdrant.index.hnsw import HnswIndex
from miniqdrant.models import Point, validate_point

cfg = CollectionConfig(
    2, Distance.DOT,
    hnsw=HnswConfig(
        m=2, ef_construct=4, ef_search=3, seed=7
    ),
)
points = [
    validate_point(Point(i, (float(i), 1.0), {}), cfg)
    for i in range(1, 7)
]
index = HnswIndex.build(
    points, distance=cfg.distance, config=cfg.hnsw
)
graph = index.export_graph()
result = index.search((1.0, 0.0), limit=3)
print("entry/max-level:", graph.entry_point, graph.max_level)
print("levels:", sorted(graph.levels.items()))
print("layer-0-degrees:",
      sorted((i, len(n)) for i, n in graph.layers[0].items()))
print("hits:",
      [(c.point_id, c.score) for c in result.candidates])
print("visited:", result.visited_count)
PY
```

实测输出：

```text
entry/max-level: 3 4
levels: [(1, 0), (2, 0), (3, 4), (4, 1), (5, 4), (6, 0)]
layer-0-degrees: [(1, 0), (2, 0), (3, 0), (4, 2), (5, 2), (6, 2)]
hits: [(6, 6.0), (5, 5.0), (4, 4.0)]
visited: 4
```

Seed 让 level/entry 可重复。所有 layer-zero degree 至多 `m=2`；零度 node 暴露简单
pruning 产生的断连分量。对 `(1, 0)` 的 dot score 让第一坐标更大者排名更高。搜索
访问 6 个点中的 4 个——这是检查数据，不是通用性能比例。本实验不使用 socket，
已在本仓库实跑。

## 练习

### 理解题

1. 为什么增大 `ef_search` 可能提高 recall，也增加工作量？
2. 为什么 nearest-only pruning 比 diversity-aware heuristic 更容易断图？

??? note "参考答案"

    1. 更大收敛窗口保留/展开更多替代路线，有希望的路线不易过早丢弃；代价是更多
       score 与 node visit。
    2. 最近邻可能都指向同一局部 cluster；多样性邻居会刻意保留通向其他区域的
       路线，即使它不是绝对最近。

### 动手题

3. 把实验改为 `m=3`。验收：所有 degree 至多 3、结果仍按 score 排序，并报告
   `visited_count` 是否变化。
4. 同一 fixture 用 seed 7 跑两次、seed 8 跑一次。验收：相同 seed 导出 graph
   相等；记录不同 seed 是否改变 level；不改 `src/`。

??? note "参考解法"

    第 3 题只改 `m` 并保证 `ef_construct >= m`。断言
    `all(len(n) <= 3 for n in graph.layers[0].values())`，实际比较 visit count，
    不预设变化方向。

    第 4 题把构建放进接收 `seed` 的 helper，断言
    `build(7).export_graph() == build(7).export_graph()`，再比较 seed 8 的
    `levels`。Hash level 对每个 seed 确定，但不会跨 seed 固定。

## 小结

MiniQdrant HNSW 构造确定性分层邻近图，在上层 greedy descent，在 layer 0 的 `ef`
窗口内收敛，并把 degree prune 到 `m`。Nearest-only pruning 与穷举断连分量
restart 偏向可检查性而非生产行为，持久 graph 也会在 open 时重建。第 6 章将从
vector navigation 转向 payload filtering 以及围绕它的 candidates+residual 合同。
