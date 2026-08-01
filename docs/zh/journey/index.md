# 自主重建

每个 Stage 都是一节可独立浏览的完整课：先理解当前问题、基本概念与必要性，再按机制板块连接相关文件和关键语句，最后用验证证据和自己的话完成理解闭环。

这是三种学习模式中的浏览器自主学习路径。按主题学习请进入[机制教程](../index.md)；需要 CLI 互动请查看 [Agent 带教使用教程](../agent-guide.md)。

如果希望在编辑器里聚焦当前增量，运行 `python -m journey.tools.build_journey study N`，再打开 `../MiniQdrant-journey-workspace`。

| Stage | 主题 | 新增测试 | 教材章节 |
|---:|---|---:|---:|
| [01](stage-01.md) | 领域契约 | 2 | [2](../tutorial/02-points-payload.md) |
| [02](stage-02.md) | 距离评分与 Top-k | 2 | [2](../tutorial/02-points-payload.md) |
| [03](stage-03.md) | 结构化 Payload 过滤 | 1 | [6](../tutorial/06-filtering.md) |
| [04](stage-04.md) | 精确可变 Segment | 2 | [4](../tutorial/04-segments.md) |
| [05](stage-05.md) | Collection 操作闭环 | 2 | [2](../tutorial/02-points-payload.md) |
| [06](stage-06.md) | 过滤感知查询规划 | 3 | [7](../tutorial/07-planner.md) |
| [07](stage-07.md) | 确定性 HNSW 搜索 | 3 | [5](../tutorial/05-hnsw.md) |
| [08](stage-08.md) | 版本化不可变 Segment | 2 | [4](../tutorial/04-segments.md) |
| [09](stage-09.md) | 分帧预写日志 | 3 | [3](../tutorial/03-wal-manifest.md) |
| [10](stage-10.md) | Manifest 发布与恢复 | 6 | [3](../tutorial/03-wal-manifest.md) |
| [11](stage-11.md) | 在线 Segment 优化 | 5 | [9](../tutorial/09-optimizer.md) |
| [12](stage-12.md) | 量化候选精排 | 2 | [8](../tutorial/08-quantization.md) |
| [13](stage-13.md) | 原子 Snapshot 与 Restore | 3 | [10](../tutorial/10-snapshots-methodology.md) |
| [14](stage-14.md) | 并发与验收闭环 | 9 | [9](../tutorial/09-optimizer.md) |
| [15](stage-15.md) | 可执行向量搜索实验 | 1 | [10](../tutorial/10-snapshots-methodology.md) |
