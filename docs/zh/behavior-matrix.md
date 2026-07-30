# 行为与证据矩阵

> **语言**: [English](../behavior-matrix.md) | 简体中文

下列每项保留的项目声明都会给出其实现边界、直接证据、适用时的故障/质量实验，以及
与 Qdrant 有意保留的差异。

## 产品目标

| 目标（Goal） | 公共 API / 模块 | 直接测试 | 故障或质量证据 | 范围内差异 |
|---|---|---|---|---|
| 固定集合模式（schema） | `Database.create_collection`, `CollectionConfig` | `tests/unit/test_domain.py`, `tests/contract/test_collection.py` | 重新打开时检查模式指纹 | 仅支持一种稠密向量模式 |
| 精确且确定性的 Top-K | `Collection.search(exact=True)`, `PlainVectorIndex`, `TopK` | `tests/unit/test_metrics.py`, `test_topk.py`, `tests/acceptance/test_exact_collection.py` | 暴力搜索与平局顺序夹具 | Python 参考算术，不使用 SIMD |
| 确定性 HNSW | `HnswIndex`, `ImmutableSegment.search` | `tests/index/test_hnsw_graph.py`, `test_hnsw_search.py` | `test_hnsw_recall.py`, 确定性召回率实验 | 教学图，而非 Qdrant HNSW/ACORN |
| JSON 载荷过滤器 | `Filter`, `Match`, `Range`, `HasId` | `tests/contract/test_filters.py` | 有索引/无索引一致性 | 不支持文本、地理、日期时间或嵌套对象索引 |
| 基数规划（cardinality planning） | `QueryPlanner`, `PayloadIndexSet` | `tests/query/test_planner.py`, `test_payload_index.py` | `test_plan_parity.py` | 固定且可检查的阈值 |
| 载荷变更 | `replace_payload`, `merge_payload`, `delete_payload_keys` | `tests/contract/test_collection.py` | 同一测试中的关闭/重开重放 | WAL 存储完整点镜像；只进行浅层顶级字段编辑 |
| 可变/不可变生命周期 | `MutableSegment`, `ImmutableSegment`, `flush` | `tests/contract/test_mutable_segment.py`, `tests/storage/test_segment_codec.py` | 跨分段验收 | 活跃分段位于内存；使用自定义不可变格式 |
| 版本与墓碑（tombstones） | WAL sequence, `StoredPoint.version` | `tests/acceptance/test_cross_segment_search.py` | 大量失效候选回归；删除覆盖 | 由单个进程分配版本 |
| 应用前先写 WAL 的恢复 | `Wal`, `Collection.upsert/delete` | `tests/storage/test_wal_codec.py`, `tests/reliability/test_wal_replay.py` | 损坏尾部与崩溃边界注入 | 单个 WAL 文件；间隔策略并非生产级刷写器 |
| 在线优化 | `optimize`, `merge`, `vacuum`, `OptimizationGate` | `tests/storage/test_merge.py`, `test_vacuum.py` | 延迟写入、旧读取者、发布失败测试 | 显式完整重写；策略是纯确定性教学组件 |
| 安全回收 | `CollectionView`, `SegmentHandle` | `tests/concurrency/test_online_optimize.py` | 视图释放前旧路径仍存在 | 进程内引用计数 |
| 标量量化（scalar quantization） | `ScalarQuantizer`, `ScalarQuantizedIndex` | `tests/index/test_quantization.py` | 精确重评分及 ≥0.95 召回率下限 | 扫描编码后的候选；打开时重建编码 |
| 快照与恢复 | `create_snapshot`, `Database.restore_collection` | `tests/acceptance/test_snapshot_roundtrip.py` | 校验和损坏、创建失败、恢复回滚 | 自定义集合快照；目标数据库不得有其他写入者 |
| 薄适配器与实验 | `miniqdrant` CLI, `miniqdrant.labs` | `tests/acceptance/test_cli.py`, `test_labs.py` | 固定种子和有界夹具 | 不提供 REST/gRPC 服务器 |

## 必需不变量

| 不变量（Invariant） | 强制机制 | 证据 |
|---|---|---|
| 维度/度量永不改变 | 冻结配置与持久化指纹 | 领域与重启测试 |
| 向量分量均为有限数 | 追加 WAL 前调用 `validate_vector` | `tests/unit/test_domain.py` |
| 余弦向量只归一化一次 | 验证过程存储归一化向量 | 度量/领域测试 |
| 版本严格递增 | 连续 WAL 序列即变更版本 | WAL 编解码/重放测试 |
| 最大可见版本胜出 | 视图级 `_latest_records` | 跨分段测试 |
| 最大墓碑阻止复活 | 拒绝候选版本 | 删除覆盖与清理测试 |
| 一个分段对每个 ID 只保留一个最高版本镜像 | 不可变 `_highest_versions`；可变版本守卫 | 可变分段/分段编解码测试 |
| 索引候选与剩余条件求值等价 | 候选集合加剩余过滤器 | 过滤器与计划一致性测试 |
| 精确排序与暴力搜索一致 | 基本评分加有界 Top-K | 精确集合/度量测试 |
| HNSW 输出排除已删除项和被过滤项 | 载荷候选准入与活跃记录 | HNSW 计划/搜索测试 |
| 一次搜索使用一个稳定视图 | `capture_view` 对句柄和可变记录取快照 | 在线优化器读取者测试 |
| 发布全有或全无 | 临时文件、fsync、替换 `CURRENT` | 清单与优化器发布注入 |
| WAL 序列唯一且有序 | 帧扫描验证序列连续 | WAL 编解码/尾部测试 |
| 重放边界得到表示 | 在清单前发布 flush/优化器分段 | 崩溃边界与重启测试 |
| 重放是幂等的 | 分段/可变分段最大版本守卫 | WAL 重放与跨重启测试 |
| 优化器不能覆盖更晚的写入 | 边界后的可变分段重建 | 带门控的延迟写入测试 |
| 过时路径等待读取者 | `SegmentHandle` 引用 | 既有视图合并测试 |
| 恢复操作先验证后替换 | 校验和、分阶段 `Collection.open`、回滚 | 快照恢复失败测试 |
| 量化结果使用原始浮点数 | 过采样后调用 `score(... original vector)` | 量化重评分测试 |
| 关闭等待所拥有的工作 | 优化器锁和活跃视图条件 | 生命周期并发测试 |
| 持久化分段 ID 无法逃逸根目录 | 清单 ID 格式与唯一性验证 | 清单路径遍历测试 |

## 声明边界

“原子”（Atomic）指经命名故障注入测试的单文件系统重命名/发布边界，并非分布式事务。
“持久”（Durable）指所选本地 WAL 策略和文档记录的 fsync 点。MiniQdrant 不声明
适合生产使用、兼容 Qdrant、支持多进程写入安全性、复制或共识，也不声明在硬件/
文件系统故障下零数据丢失。
