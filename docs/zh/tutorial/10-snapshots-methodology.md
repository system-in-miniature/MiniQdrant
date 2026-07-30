# 第 10 章：快照与方法论

> [English](../../tutorial/10-snapshots-methodology.md) · 中文

一个 collection 能持久化，不等于它能移植。current manifest、被引用的 segment、metadata 与 WAL 必须一起移动；restore 还必须在替换健康数据之前拒绝损坏。MiniQdrant snapshot 用 SHA-256 文件索引打包这些状态，以原子 rename 发布包，再通过 staged open-and-validate 协议恢复。本书最后一章还会把仓库行为矩阵变成一种可复用的“小系统”研究方法。

## 学习目标

完成本章后，你应当能够：

1. 列出 MiniQdrant collection snapshot 包含的文件；
2. 跟踪 snapshot creation 的 flush、checksum、fsync、rename；
3. 跟踪 restore 的 checksum validation、staged open、backup、publication、rollback；
4. 准确表述原子性与并发主张的边界；
5. 用实现、直接测试、失败测试和声明差异来评价系统主张。

## 1. 建立一致的源状态

公开入口是 `src/miniqdrant/collection.py::Collection.create_snapshot`。它先检查 collection lifecycle，再 acquire `_optimizer_lock` 与 `_update_lock`；在这个边界内调用 `flush()`、flush WAL，再调用 `create_collection_snapshot()`。

锁很重要。snapshot 不能在 optimizer 或 flush 正发布另一 generation 时复制 manifest。因为锁可重入，`create_snapshot()` 能安全调用 `flush()`。flush 把当前 mutable record 移入 immutable segment，并推进 manifest 的 `replay_boundary`；flush WAL 则在复制文件前建立所选本地 durability 边界。

这不会阻止另一个进程修改同一 collection 目录。MiniQdrant 的合同是每个 collection 一个进程、一个 writer。

## 2. 创建带 checksum 的包

`src/miniqdrant/persistence/snapshot.py::create_collection_snapshot` 拒绝已存在的 destination，创建一个临时 sibling 目录，只复制 current manifest 可达的状态：

- `collection.json`；
- `CURRENT`；
- 被引用的 immutable manifest generation；
- `wal/` 目录；
- `manifest.segment_ids` 命名的每个 segment 目录。

复制被引用段而不是整个 collection 目录，能避开 retired 或 abandoned path。随后函数遍历复制后 `collection/` 下每个文件，构造：

```python
files = {
    path.relative_to(collection).as_posix(): _sha256(path)
    for path in sorted(collection.rglob("*"))
    if path.is_file()
}
```

它把 `format_version=1` 和 relative-path-to-digest 映射以 canonical JSON 写入 `snapshot.json`。`_sha256()` 以 1 MiB chunk 流式读取；`_fsync_tree()` fsync 文件和目录，包括临时根目录。完成这些步骤后，`os.replace(temporary, destination)` 才发布 snapshot，随后 fsync destination 的 parent directory。

发布前任何步骤失败，`except BaseException` 都会删除临时树。`tests/reliability/test_snapshot_restore_failure.py::test_snapshot_publish_failure_leaves_no_partial_target` 在 `before_snapshot_publish` 注入失败，验证 destination 从未出现。

这里的“原子创建 snapshot”是指：同一文件系统内的目录 rename 在一个本地发布边界使完整包可见。它不是分布式事务，也不保证免疫所有文件系统或硬件故障。

## 3. Restore 前先验证

`src/miniqdrant/persistence/snapshot.py::validate_collection_snapshot` resolve snapshot path，并分层验证：

1. 解析 `snapshot.json`，要求 format version 为 1；
2. 要求索引文件集与实际 collection 文件集完全相等；
3. 重算每个 SHA-256 digest；
4. 读取 collection metadata 与 current manifest；
5. 对比 manifest schema fingerprint 和 `config_fingerprint(metadata.config)`；
6. 解码每个被引用 segment，要求其 config 等于 collection config。

文件集严格相等能同时发现缺失文件和未被索引的额外文件；checksum 发现内容变化；后续语义读取则发现“checksum 自洽但系统关系不一致”的包，例如 manifest 或 segment 来自另一 schema。意外解析和 I/O 失败会包装为 `SnapshotError`，已有 `SnapshotError` 则保持原样。

validation 返回嵌套的 `collection/` 目录，不返回 live `Collection`；publication 属于 database 层。

## 4. Staged restore 与 rollback

`src/miniqdrant/database.py::Database.restore_collection` 是 class method，因此可在 target `Database` 拥有 collection 之前执行 restore。它先校验新 collection 名，并在触碰已有 target **之前** 调用 `validate_collection_snapshot()`。

restore 协议如下：

1. 在 `database/collections/` 下创建临时 sibling；
2. 把已验证 collection 复制进 staging；
3. 用请求的 target 名改写 `collection.json`；
4. 调用 `Collection.open(stage)` 再 close，强制执行正常恢复与语义验证；
5. fsync staged directory；
6. 若是 replace，把旧 target 原子 rename 为唯一 backup；
7. 把 staging rename 为 target，并 fsync collections directory；
8. 只有发布成功后才删除 backup。

若 target publication 失败，内层 exception handler 会在可能时把 backup rename 回去；外层 handler 删除 staging。因此，无效或失败的 restore 不会悄悄摧毁上一 collection。

还有一项操作前提：target database 不得有另一个 writer，也不能有仍在服务并修改旧目录的内存 `Collection`。代码无法跨进程协调。使用 `replace=True` 前，调用者应关闭 target database。

## 5. 与真实 Qdrant 对照

真实 Qdrant 通过 REST API 暴露 collection 与 shard snapshot 操作，例如创建 collection snapshot、从 snapshot 恢复。其实现参与 collection、shard、replica 与分布式传输工作流；源码责任位于 collection snapshot 和 storage content-manager 模块一带。Qdrant snapshot 使用自己的格式与操作合同。

MiniQdrant 保留了若干可识别的不变量：

- snapshot 一致的已发布 collection state；
- 用 cryptographic digest 索引内容；
- 在 staging 构建；
- replacement 前验证；
- 使用本地原子 publication；
- publication 失败时回滚上一 target。

它省略或改变了产品行为：

- 格式私有且不兼容 Qdrant；
- 只打包一个本地 collection root；
- 没有 shard、replica、consensus、远程 snapshot storage、API authentication 或 cluster coordination；
- `replace` 假定不存在竞争 writer；
- SHA-256 integrity 不是 authenticity 或 encryption；
- 本地 fsync/rename 主张不代表分布式 durability。

参见[行为矩阵](../behavior-matrix.md)的 snapshot 行与 claim boundary、[完整差异文档](https://github.com/system-in-miniature/mini-qdrant/blob/main/DIFFERENCES_FROM_QDRANT.md)的 product-scope snapshot 行、[Qdrant 映射](../qdrant-mapping.md)的 snapshot 条目，以及[存储格式](../storage-format.md)中的具体目录树。

## 6. 动手实验

### 实验 A：检查并恢复 snapshot

```bash
UV_CACHE_DIR=/tmp/miniqdrant-uv-cache uv run python - <<'PY'
from pathlib import Path
from tempfile import TemporaryDirectory
import json

from miniqdrant import Database, Distance, Point, SearchRequest

with TemporaryDirectory() as root:
    root = Path(root)
    db = Database.open(root / "live")
    collection = db.create_collection("items", dimension=2, distance=Distance.DOT)
    collection.upsert([Point(7, (1.0, 0.0), {"kind": "book"})])
    snapshot = collection.create_snapshot(root / "snapshot")
    index = json.loads((snapshot / "snapshot.json").read_text())
    print("format version:", index["format_version"])
    print("indexed file count:", len(index["files"]))
    print("all digests are SHA-256:", all(len(value) == 64 for value in index["files"].values()))
    db.close()
    Database.restore_collection(snapshot, root / "restored-db", "copy")
    restored_db = Database.open(root / "restored-db")
    hits = restored_db.collection("copy").search(SearchRequest((1.0, 0.0), 1)).hits
    print("restored ids:", [hit.id for hit in hits])
    restored_db.close()
PY
```

实测输出：

```text
format version: 1
indexed file count: 11
all digests are SHA-256: True
restored ids: [7]
```

实际 segment 目录含随机 UUID，所以实验报告稳定属性，而不报告不稳定文件名。

### 实验 B：执行成功与失败边界

```bash
UV_CACHE_DIR=/tmp/miniqdrant-uv-cache uv run pytest -q tests/reliability/test_snapshot.py tests/reliability/test_snapshot_restore_failure.py tests/acceptance/test_snapshot_roundtrip.py
```

实测输出：

```text
.....                                                                    [100%]
5 passed in 2.28s
```

这些测试覆盖可搜索 restore、checksum corruption、snapshot publication 失败、带 rollback 的 restore publication 失败，以及 source database 关闭后的可移植性。

## 7. 面向“小系统”的行为矩阵方法

小实现只有在保留重要机制、又不伪装被删层次时才有价值。MiniQdrant 的 [`docs/behavior-matrix.md`](../behavior-matrix.md)用四列评价每项 product goal：

1. **实现边界**：拥有它的公开 API 或 symbol；
2. **直接测试**：正常行为工作的证据；
3. **失败或质量证据**：corruption、concurrency、recovery 或 recall 检查；
4. **范围差异**：证据不能建立什么主张。

把这个结构应用于 snapshot：

| 问题 | 仓库证据 |
|---|---|
| 在哪里实现？ | `create_collection_snapshot`、`validate_collection_snapshot`、`Database.restore_collection` |
| 正常路径工作吗？ | `test_snapshot_restores_searchable_collection`、`test_snapshot_roundtrip_survives_source_removal` |
| 失败时怎样？ | checksum corruption、pre-publish failure、restore rollback 测试 |
| 什么仍超出范围？ | Qdrant 格式/API 兼容、multi-writer 和分布式协调 |

该方法能防止两个常见错误。第一，class 或 strategy 名不是“对应机制实际运行”的证据；第 8 章量化 “HNSW” 分支就是反例。第二，通过本地测试不能为被省略的生产层提供证据；snapshot round-trip 不证明分布式 snapshot coordination。

扩展 MiniQdrant 时，应在实现前先写 behavior row：命名 invariant、owner、direct test、hostile test 和明确产品边界。然后实现能让五项陈述都成立的最小 source-like architecture。任何既有 simplification 发生变化时，同步更新 differences 和 mapping。

## 8. 练习

1. **理解题：**为什么 SHA-256 文件索引能发现 corruption，却不能证明谁创建了 snapshot？
2. **理解题：**restore 为何要在发布前 open 再 close staged collection？
3. **动手失败设计题：**在 scratch diff 中，于旧 target rename 为 backup 后、staging 发布前立即增加 failure injection。不要修改 `src/`。验收标准：说明期望目录状态、reopen 后 point ID，以及证明 rollback 后没有 staging/backup 残留的测试。
4. **方法论题：**为新增 sparse vector 起草一行 behavior matrix，并包含与真实 Qdrant 的诚实差异。

??? note "参考答案"

    1. digest 把 path 与观测 bytes 绑定，使偶然或无密钥内容变化可检测。能同时替换内容与 `snapshot.json` 的人也能计算新 digest。Authenticity 需要可信 signature 或 MAC，以及 key-management policy。
    2. 它复用正常 `Collection.open()` 恢复路径，在目录成为 target 前校验 WAL、manifest、segment codec、schema 与 lifecycle。checksum 本身不能证明这些语义关系。
    3. 现有内层 `try` 已描述目标结果：注入失败后把 backup rename 回 target，删除 staging，原始 ID 保持可搜索。聚焦测试可扩展 `test_restore_publish_failure_rolls_back_previous_collection`，断言 `collections/items` 含原始点，且不存在 `.items-restore-*` 或 `.items-backup-*`。验收命令：`UV_CACHE_DIR=/tmp/miniqdrant-uv-cache uv run pytest -q tests/reliability/test_snapshot_restore_failure.py`。
    4. 示例：goal 为“sparse-vector 精确检索”；owner 为 `Collection.search` 加 source-like sparse index boundary；direct test 对照 brute-force sparse dot product；failure/quality evidence 覆盖 malformed indices、duplicate dimensions、restart 与 deterministic ties；scoped difference 为“一个本地 sparse vector 与精确 Python 打分，不含 Qdrant named vectors、hybrid fusion、native sparse index、REST/gRPC schema 或 distributed shards”。

## 小结

MiniQdrant snapshot 捕获 manifest 可达的 collection state，以 SHA-256 索引每个文件，fsync 后 rename 完整包，同时校验 bytes 与 schema 关系，并通过 staged normal open 加 rollback 来 restore。其主张刻意限制在本地单 writer。纵观全书，持久的方法始终相同：定位机制 owner、显式写出状态转换、运行直接与 hostile 测试、对照真实系统，并记录证据不能支持的主张。这样，system in miniature 才会成为可信学习工具，而不是套着生产名字的玩具。
