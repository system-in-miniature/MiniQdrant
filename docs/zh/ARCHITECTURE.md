> **Language**: [English](../architecture.md) | 简体中文

# 架构

## 运行时所有权

```text
Database
  └─ Collection (update order, current manifest, optimizer, lifecycle)
       ├─ WAL (durable operation sequence)
       ├─ MutableSegment (newest unflushed versions)
       ├─ SegmentHandle[] (published immutable segments)
       ├─ QueryPlanner (per-segment strategy)
       └─ ManifestStore (atomic restart root)
```

`Database` 拥有集合目录及其生命周期。`Collection` 是唯一允许对更新排序或发布分段集合的组件。索引绝不会直接写入存储根。

## 变更与可见性

一个插入或更新（upsert）/删除批次会先得到完整验证，再作为一项 WAL 操作追加，之后才应用到可变分段。载荷替换、合并和键删除操作会生成一个完整的新点映像，并复用同一套 upsert WAL 契约。WAL 序列号就是其版本。
每次读取都会针对每个外部点 ID 计算版本最大的记录；最大版本的墓碑（tombstone）会隐藏所有更旧的映像。

```text
validate whole batch → append WAL frame → durability action → apply version
```

余弦向量会在验证时归一化。所有内部度量分数都采用越高越好的约定，并使用规范 ID 打破平局。

## 搜索

`capture_view()` 会获取带引用计数的不可变句柄，并在持有短时集合锁期间创建可变记录的快照。随后，距离计算在不持有该锁的情况下运行。

对每个分段而言，载荷索引会给出候选集合和基数估计。规划器会选择精确扫描、先过滤后精确扫描、HNSW、过滤式 HNSW，或者量化候选评分加精确重评分。集合会按版本丢弃过时的分段候选，然后执行一次最终的、有界的全局 Top-K。

## 在线优化

```text
capture source handles + WAL version V
→ build replacement outside update lock
→ reacquire update lock
→ retain mutable records newer than V
→ publish one new manifest/CURRENT
→ retire source handles
→ delete source paths after the last old view closes
```

`optimizer/policy.py` 包含一个确定性的教学策略：它优先处理过多墓碑，其次是在分段数量超过目标时处理两个最小分段，最后处理较大的未索引分段。测试会直接执行该策略，但它没有接入 `Collection`：`flush_threshold_points` 不会触发自动刷写，而显式调用 `merge()`、`vacuum()` 和 `optimize()` 总会强制进行一次完整且安全的重写。

## 持久化与恢复

持久化根是 `CURRENT`，它指向一份带校验和的清单。清单列出不可变分段目录和 WAL 重放边界。启动时会验证恢复根和分段，然后以幂等方式重放其后的 WAL 帧。

只有不完整或校验和错误的活动 WAL 尾部可以被截断。尾部之前的损坏会被拒绝。创建快照时，会先刷写可变分段，只复制清单引用的数据与 WAL，记录 SHA-256 校验和，执行 fsync，然后原子重命名。恢复操作会先验证再替换目标，并在发布之前打开暂存集合。

## 并发模型

每个集合内的更新会串行执行。搜索者使用稳定视图。同一时间只运行一个优化器，但其开销高昂的构建阶段不会持有更新锁。该设计在这些边界内是线程安全的；它不是一个多进程写入协议。
