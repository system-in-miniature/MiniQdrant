# MiniQdrant：机制优先教程

本书跟随一个 point 从 direct API 进入持久历史、immutable segment、索引、规划、
优化和快照。请按顺序阅读：每章都会建立下一章依赖的不变量。每个机制都锚定到
MiniQdrant 的源码相对路径与函数，与真实 Qdrant 对照，并配有在本仓库实跑的实验。
MiniQdrant 是单进程教学参考实现，不是兼容 Qdrant 的服务器。

## 全书目录

1. [认识 MiniQdrant](01-getting-started.md)——定位、环境、创建 collection、
   upsert 与第一次搜索。
2. [点与负载](02-points-payload.md)——值模型、不可变 JSON payload、校验与
   Euclid 负平方分数。
3. [WAL 与清单](03-wal-manifest.md)——带校验和帧、fsync 策略、原子 `CURRENT`
   发布与 `replay_boundary`。
4. [段生命周期](04-segments.md)——mutable→immutable flush、最高版本可见性、
   tombstone 与稳定读者 handle。
5. [HNSW](05-hnsw.md)——确定性 level、greedy descent、`ef` 收敛、degree pruning
   与非标准 restart。
6. [过滤](06-filtering.md)——payload index、`must`/`should`/`must_not` 与
   candidates+residual 合同。
7. [查询规划](07-planner.md)——基数估计、五种策略与可观察 plan/work 证据。
8. [量化](08-quantization.md)——scalar int8、oversample+rescore 与当前全扫描
   candidate 路径。
9. [在线优化](09-optimizer.md)——merge、vacuum、rebuild、短发布锁、晚写保留与
   flush/optimize 互斥。
10. [快照与方法论](10-snapshots-methodology.md)——SHA-256 inventory、staged
    restore 与行为矩阵驱动工程。

## 如何使用本书

使用 Python 3.12+ 和 `uv`，从仓库根目录运行命令。除非章节明确说明，实验都使用
临时目录与 direct API。[行为矩阵](../behavior-matrix.md)是证据索引；
[Qdrant 映射](../qdrant-mapping.md)分类语义关系；
[与 Qdrant 的差异](https://github.com/system-in-miniature/mini-qdrant/blob/main/DIFFERENCES_FROM_QDRANT.md)定义声明边界。

动手题答案折叠在 `??? note` 中。先尝试任务并运行验收命令，再展开参考答案。练习
会描述 patch 或临时脚本，但阅读完成态参考仓库时，不要求修改 `src/`。
