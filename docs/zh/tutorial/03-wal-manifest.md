# 第 3 章 · WAL 与清单

持久性首先是一种顺序声明。MiniQdrant 不能先在内存暴露已确认 point，再决定是否
记录它；崩溃后也不能重开一组发布到一半的 segment 文件。预写日志（WAL）、不可变
manifest 代次和 `CURRENT` 根指针分别解决这两个边界问题。

## 学习目标

学完本章后，你能够：

1. 把 upsert 从校验追踪到 WAL 追加，再到 mutable apply；
2. 描述带校验和 WAL 帧及其尾部修复规则；
3. 解释三种本地持久策略而不夸大；
4. 指出 `CURRENT` 是原子 manifest 提交点；以及
5. 推导 `replay_boundary` 为何让 segment 状态和 WAL replay 幂等。

## WAL 先于 apply

`src/miniqdrant/collection.py::Collection.upsert` 校验整个批次，取得
`_update_lock`，先调用 `Wal.append(UpsertOperation(batch))`，再调用
`_apply_wal_record`。删除用 `DeleteOperation` 遵循相同顺序；payload 变更最终也是
完整 point 镜像的 upsert。核心写入不变量是：在所选持久策略下，任何已接受变更都
必须先追加 WAL 帧，之后才能进入 mutable segment。

`src/miniqdrant/persistence/wal.py::Wal.append` 递增连续序列，把操作序列化成规范紧凑
JSON，通过 `encode_frame` 包帧，写入活跃 stream，并按策略调用 `os.fsync`。然后
它才更新进程内最后序列并返回 `WalRecord`。`Collection._apply_wal_record` 用该序列
作为批次中每个 point 的版本。

一个序列可以在 collection 更新锁下为多个点统一定版，但 MiniQdrant 没有通用事务
协议。序列是排序/replay 坐标，不是分布式时间戳。

### 带校验和的帧

`src/miniqdrant/persistence/frame.py::encode_frame` 的布局为：

```text
magic | 格式版本 | body 长度 | sequence | kind | JSON payload | CRC32
```

CRC 覆盖 sequence、operation kind 和 payload。打开时，`frame.py::scan_frames`
检查 magic、版本、最大尺寸、body 边界、CRC 与最小 body 前缀；
`wal.py::_validate_sequences` 随后要求帧从序列 1 开始严格连续。

崩溃修复刻意很窄：不完整的最后一帧可截断到最后有效边界；启用 repair 时，CRC
错误的最后一帧也可截断。中间帧损坏绝不会被静默丢弃，因为那会连带抛弃之后看似
已持久的历史。`_truncate` 会 flush 并 fsync 修复后的长度，然后才继续 replay。

这个区别把合理的 torn append 与任意持久损坏分开。WAL 不承诺恢复所有坏文件，只
承诺修复其追加协议能够证明合理的故障形态。

## 三种本地持久策略

`src/miniqdrant/persistence/wal.py::Durability` 有三个值：

- `ALWAYS`：`Wal.append` 每帧返回前 fsync。
- `INTERVAL`：append 写入字节，但本参考运行时没有生产级后台定时 flusher；之后
  的显式 flush 或干净 close 才越过 fsync 边界。
- `MANUAL`：调用者依赖 `Wal.flush`、collection close、flush/snapshot 协调或自己
  选择的边界。

这些名称用于教学“确认延迟 vs 进程/主机故障后可能丢失”的权衡。它们不是 Qdrant
写一致性级别，也不涉及副本。尤其不能把 `INTERVAL` 描述为完整生产调度器。
[`WAL-before-apply 恢复`](../behavior-matrix.md#行为矩阵)条目明确写出了这一点。

`Collection.close` 等待自有工作、flush WAL 并关闭；`simulate_process_loss` 不做
显式 flush 就关闭，供可靠性实验使用。普通关机和崩溃模拟不应意外具有相同语义。

## Segment 发布需要第二个提交边界

WAL 让近期变更可 replay；immutable segment 让旧状态可快速加载与搜索。Flush
不能只是写 segment 再删内存。恢复需要一个权威的完整 segment 列表，以及已被它们
表示的 WAL 位置。

`Collection.flush` 从 mutable records 构造 `SegmentImage`，调用
`src/miniqdrant/segment/codec.py::SegmentCodec.write_atomic`，再构造新 `Manifest`。
Manifest 增加 generation、保留 schema fingerprint、追加新 segment ID，并把
`replay_boundary` 设为 `Wal.last_sequence`。只有 `ManifestStore.publish` 成功后，
live collection 才追加新 `SegmentHandle`、安装 manifest 并替换 mutable segment。

`src/miniqdrant/persistence/manifest.py::ManifestStore.publish` 分两阶段：

1. 编码带校验和的不可变 manifest generation，写入并 fsync 临时文件，rename 到
   最终名，再 fsync 目录；
2. 写入并 fsync `CURRENT.tmp`，经过测试故障注入边界，替换 `CURRENT`，再次 fsync
   目录。

`CURRENT` 只包含一个 manifest 文件名，其 rename 是唯一发布提交点。重启只会看到
旧完整 generation 或新完整 generation，不会看到半新半旧的 segment ID 列表。
`Manifest.__post_init__` 还拒绝重复/不安全 segment ID，schema fingerprint 则
阻止用不同 collection 配置重开 segment。

这里的“原子”指经过测试的同文件系统 rename/发布边界，不是分布式事务；硬件与文件
系统保证仍然重要。声明边界见[必要不变量](../behavior-matrix.md#必要不变量)。

## 从 manifest 边界之后 replay

`Collection.open` 读取 collection metadata，加载 `CURRENT`，检查 schema
fingerprint，打开列出的各 segment，再打开 WAL。随后执行：

```python
for record in wal.replay(after_sequence=manifest.replay_boundary):
    collection._apply_wal_record(record)
```

假设 manifest 含有截至序列 40 的 segment 状态。重放 1–40 是重复工作，跳过 41
则会丢失后续已确认写。`replay_boundary=40` 精确声明已表示的前缀，因此 replay
从 41 开始。

还有第二层幂等性：当同 ID 已有相等或更新版本时，
`MutableSegment.apply_upsert`/`apply_delete` 会忽略记录；immutable 构造也只保留
每个 ID 的最高版本。这些 guard 防止重复历史镜像变得可见，但不能替错误 replay
边界开脱：manifest 仍然必须只引用持久发布的 segment 状态。

### 沿崩溃时间线推理

审计协议最简单的方法是在命名边界暂停。若进程在 `Wal.append` 前死亡，内存和恢复
都没有操作。在 `ALWAYS` 下，若 WAL fsync 后、mutable apply 前死亡，调用者可能
看到失败，reopen 却会 replay 持久帧。因此 retry 应被视为新的版本化 upsert，不能
用来证明第一次尝试从未发生。

Flush 期间，写临时 segment 时崩溃仍由旧 manifest 掌权。已完成但尚未被已发布
manifest 命名的 segment 是 orphan，不是可见状态。新 manifest 文件持久后但
`CURRENT` 替换前崩溃，仍选择旧 generation；`CURRENT` 替换后崩溃，则选择新
generation 并跳过截至 replay boundary 的 WAL records。

这些结果依赖发布顺序。清理 temporary/orphan object 是运维卫生，不能成为判断逻辑
真相的前提；只有根指针决定恢复信任哪个完整 generation。
`tests/reliability/test_crash_boundaries.py` 与 `test_manifest_publish.py` 在这些阶段
注入故障，`tests/reliability/test_wal_replay.py` 检查 replay 结果。先读故障时间线
再读清理代码是有用的系统习惯：先证明每次 crash 都选择有效状态，再证明未用文件
最终得到处理。

MiniQdrant 有意不回收已覆盖前缀。WAL 目录只有
`00000000000000000001.wal`，flush 只推进逻辑边界，文件会永久增长。编号文件名并不
证明实现了轮转。这一差异见
[与 Qdrant 的差异](https://github.com/system-in-miniature/mini-qdrant/blob/main/DIFFERENCES_FROM_QDRANT.md#其他有意简化)。

## MiniQdrant 对照真实 Qdrant

机制层教训可以迁移：write-ahead 顺序、校验和、单调操作顺序、恢复 checkpoint、
持久文件发布，以及选择一致 segment inventory 的根状态。
[`frame.py`、`wal.py`、Manifest 与 replay 映射](../qdrant-mapping.md#运行时与存储)
把这些职责标为机制层等价。

运维实现则小得多。真实 Qdrant 在 shard 机械中管理 WAL 容量和 segment 持久化，
回收安全覆盖的历史，集成后台服务，并参与副本/共识工作流。MiniQdrant 只有一个
无限增长本地文件、JSON 操作、自定义 manifest、一个进程、无副本确认；其
`INTERVAL` 也不是生产级周期 flusher。

因此成功重开证明所选策略的本地恢复合同，不证明适用于每种文件系统、存储设备、
多进程写者或分布式故障。边界越清楚，这个小实验越有价值。

## 动手实验：检查持久根

```bash
export UV_CACHE_DIR=/tmp/miniqdrant-uv-cache
uv run python - <<'PY'
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from miniqdrant import Database, Distance, Point

with TemporaryDirectory() as tmp:
    root = Path(tmp) / "db"
    db = Database.open(root)
    c = db.create_collection(
        "items", dimension=2, distance=Distance.DOT
    )
    print("upsert-sequence:",
          c.upsert([Point(1, (1, 2), {"kind": "a"})]))
    c.flush()
    current = (c.path / "CURRENT").read_text().strip()
    envelope = json.loads((c.path / current).read_text())
    payload = envelope["payload"]
    print("current:", current)
    print("manifest:", payload["generation"],
          len(payload["segment_ids"]),
          payload["replay_boundary"])
    print("wal-files:",
          sorted(p.name for p in (c.path / "wal").iterdir()))
    db.close()
    reopened = Database.open(root)
    print("reopened-count:",
          reopened.collection("items").count())
    reopened.close()
PY
```

实测输出：

```text
upsert-sequence: 1
current: manifest-00000000000000000002.json
manifest: 2 1 1
wal-files: ['00000000000000000001.wal']
reopened-count: 1
```

创建 collection 发布 generation 1；flush 发布 generation 2，含一个 segment，
replay boundary 为 1。即使首条记录已覆盖，WAL 文件仍保留。重开加载该 segment
并跳过已覆盖帧，留下一个可见点。本实验不使用 socket，已在本仓库实跑。

## 练习

### 理解题

1. 为什么只有新 manifest 持久后才能替换 `CURRENT`？
2. 为什么坏的最后 CRC 可修复，而坏的中间 CRC 必须报错？

??? note "参考答案"

    1. `CURRENT` 是恢复根。过早发布可能让重启指向缺失或不完整 generation。
       所有新引用对象持久前，旧根必须保持权威。
    2. 坏末帧可以是崩溃中断的那一次 append。坏中间帧之后还有字节，截断会静默
       丢弃看似已持久的后续历史。

### 动手题

3. 在临时脚本中 upsert 两次但不 flush，close 后 reopen 并打印两个点。验收：
   sequence 是 1 和 2，重开 count 为 2，且不修改 `src/`。
4. 在临时 WAL 尾追加三个垃圾字节，再重开数据库。验收：重开成功、垃圾尾被截断、
   原可见点仍存在；只能操作临时数据库。

??? note "参考解法"

    第 3 题依靠 `Collection.open` replay 初始 manifest 边界 0 之后的记录。

    第 4 题先干净 close，记录 WAL 大小，用 `open(path, "ab")` 追加 `b"xyz"`，
    再 reopen。`scan_frames(..., repair_tail=True)` 会移除不完整 header。断言修复
    后大小等于记录值且 count 不变。

## 小结

WAL 让每次变更先于 mutable 可见性有序落盘，并检测 torn/corrupt frame。带校验和
的不可变 manifest 描述完整 segment 集合，原子替换 `CURRENT` 则发布该集合。
`replay_boundary` 通过精确标明已表示的 WAL 前缀连接两者。第 4 章将跟随这些记录
经过 mutable flush、immutable segment 可见性、tombstone 与安全读者生命周期。
