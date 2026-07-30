> **Language**: [English](../differences.md) | 简体中文

# 与 Qdrant 的差异

MiniQdrant 保留了选定的单节点不变量，同时有意省略产品兼容性。与 Qdrant 共用的名称描述的是教学主题，并不表示实现或性能完全相同。

有关模块之间的正向对应关系，请参阅 [`docs/qdrant-mapping.md`](qdrant-mapping.md)。

## 产品范围

| Area | MiniQdrant | Qdrant |
|---|---|---|
| Access | Python API and thin local CLI | REST, gRPC, official clients |
| Vectors | one dense vector per point | dense, sparse, named, multi-vector |
| Payload indexes | keyword, integer, float, bool | broader production index set |
| Retrieval | exact, deterministic HNSW, scalar quantization | production HNSW/filtering/quantization stack |
| Storage | custom teaching WAL/segment/manifest | Qdrant formats and storage engines |
| Deployment | one process, one writer per collection | shards, replicas, distributed coordination |
| Optimizer | explicit deterministic full rebuild | adaptive background optimizers |
| Snapshot | collection root, custom checksum format | Qdrant snapshot compatibility |

未实现的功能包括：Qdrant 传输协议或存储兼容性、稀疏或混合搜索、推荐/融合/分组、滚动查询和批量搜索、地理/文本/日期时间索引、mmap/RocksDB、分片、复制、Raft、身份验证、TLS、配额、多租户、GPU、SIMD/原生内核，以及在线模式迁移。

## 已声明的语义和性能差异

1. **过滤式 HNSW 是后过滤加固定过采样。**
   `HnswIndex.search()` 在遍历图时不会查询 `allowed_ids`；只有在收集候选时才检查成员资格，并且分段最多请求 `limit * 4` 个候选。这正是 Qdrant 的过滤感知 HNSW 设计所批评的后过滤模式：选择性过滤器可能在遍历后丢弃最近的候选，导致返回的命中更少或召回率更差；增加过采样则会浪费工作，却不能保证得到足够的匹配。Qdrant 将过滤约束纳入图遍历，并针对困难过滤器采用其他策略。

2. **标量量化路径是解码浮点全扫描，而不是 HNSW 评分器。**
   MiniQdrant 会扫描每个符合条件的量化码，将量化查询和存储的编码都解码回浮点向量，对这些浮点数进行评分、过采样，并对保留下来的候选执行精确重评分。真正的 Qdrant 可以在 HNSW 遍历期间使用 int8 量化评分器，再对选定候选进行重评分。因此，MiniQdrant 教授的是两阶段近似/重评分的结构，但既不提供整数评分，也不具备生产实现的渐近优势。

3. **每次集合搜索都有 O(N) 的视图捕获成本。**
   `capture_view()` 会扫描所有不可变和可变记录来重建 `_latest_records`，并重建可变快照，其中包括载荷索引。随后，`_stale_live_count()` 会再次扫描每个已搜索的分段。因此，即使每个分段的 HNSW 只访问很少节点，端到端搜索仍然随集合大小线性增长。Qdrant 维护增量式 ID 和分段跟踪，而不是为每次查询重建全局可见性。

4. **同一个 upsert 批次内的重复 ID 采用首次写入胜出。**
   批次中的每个项目都会收到相同的 WAL 序列号/版本，而 `MutableSegment` 会拒绝同版本替换。Qdrant 对重复点 ID 的批次/更新行为采用最后写入胜出。若调用者想要类似 Qdrant 的行为，就必须自行对 MiniQdrant 批次去重。

5. **载荷字段路径会自动展开数组。**
   MiniQdrant 的路径遍历器无需显式标记就会向下遍历列表元素。Qdrant 使用显式的 `[]` 路径记法，并且具有不同的嵌套数组匹配语义，包括元素局部的嵌套条件。因此，在两个系统间复制的过滤器可能匹配到不同的点集合。

6. **欧几里得分数是负平方距离。**
   MiniQdrant 的所有度量都采用统一的内部约定，即分数越高越好，因此欧几里得度量暴露的是 `-(distance²)`。`score_threshold` 始终按 `score >= threshold` 应用；欧几里得调用者必须传入负平方距离阈值。Qdrant API 会根据所选度量解释阈值方向，因此数值阈值不可直接移植。

7. **`QUANTIZED_HNSW_RESCORE` 是一个具有误导性的策略名称。**
   选择这个计划会完全绕过 `_hnsw`，并调用 `ScalarQuantizedIndex` 的全扫描。结果中的 `plan` 可用于观察分支，但不能证明 HNSW 确实运行过。

8. **持久化的 `hnsw.bin` 在验证后会被丢弃。**
   `SegmentCodec.read()` 将图解码到 `SegmentImage.hnsw_graph`，但 `SegmentImage.to_segment()` 只传递 `indexed=True`；构建不可变分段时会从所有存活点重建 HNSW。Qdrant 的持久化索引可以复用，而这里会让打开/重启承担图构建成本，并使 `hnsw.bin` 成为只写的语义数据。

9. **HNSW 搜索可以跨不连通分量进行穷举式重启。**
   当第一次第 0 层搜索得到的分数少于 `breadth` 时，MiniQdrant 会反复从尚未访问的最小点 ID 开始。这并不是标准 HNSW 行为。在碎片化图或较大的 `ef_search` 下，它可能访问每个向量，从而在召回率测试中掩盖较差的图连通性，并使近似搜索退化为全扫描。

10. **优化器策略和自动刷写阈值没有接入运行时。**
    `choose_optimization()` 和 `flush_threshold_points` 只用于测试/配置。upsert 不会触发刷写或后台工作，而显式调用 `merge()`、`vacuum()` 和 `optimize()` 都会重写捕获到的完整分段集合。规划器还将 `indexing_threshold_points` 同时用于普通扫描和过滤扫描决策，而 Qdrant 暴露了独立的全扫描阈值。

11. **WAL 从不截断、轮转或回收已发布的历史。**
    刷写和优化会推进 `replay_boundary`，因此恢复时会跳过已经覆盖的帧，但单个 `00000000000000000001.wal` 文件会无限增长。它的编号文件名并不代表已经实现多文件轮转。Qdrant 会回收已被持久化状态安全覆盖的 WAL 历史。

## 其他有意简化

为了便于检查，HNSW 实现采用确定性的层级、平局判定和仅保留最近邻的剪枝规则，而不是追求生产级召回率与吞吐量。分段 `.bin` 文件包含分帧 JSON，而不是原生二进制或 mmap 布局。非精确载荷基数估计使用固定的教学启发式方法。`SearchRequest.filter` 的类型是 `object | None` 并在运行时检查，而不是暴露一个完全自说明的客户端模式。

持久性策略暴露的是本地崩溃边界，而不是分布式写入一致性契约。载荷字段合并/删除有意采用浅层方式；嵌套补丁语言和 Qdrant API 兼容性不在范围内。
