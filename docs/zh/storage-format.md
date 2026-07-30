> **Language**: [English](../storage-format.md) | 简体中文

# 存储格式

这些格式为 MiniQdrant 私有，并且有意与 Qdrant 不兼容。

## 集合根目录

```text
collection/
├── collection.json
├── CURRENT
├── manifest-000000000000000000NN.json
├── wal/00000000000000000001.wal
└── segments/seg-<uuid>/
    ├── meta.json
    ├── points.bin
    ├── payloads.bin
    ├── versions.bin
    ├── deleted.bin
    ├── hnsw.bin
    └── payload-indexes.bin
```

`collection.json` 存储不可变集合配置和载荷索引模式（payload index schema）。`CURRENT` 包含一个清单（manifest）文件名。清单是规范 JSON 信封，其中包含载荷的 SHA-256、代数、模式指纹、排序后的分段 ID，以及 WAL 重放边界。

## WAL 帧

所有整数均为大端序（big-endian）：

```text
magic "MQWL" (4)
format version (1)
body length (4)
sequence (8)
operation kind (1)
canonical JSON operation payload (N)
CRC32 of body (4)
```

操作类型 1 是批量插入或更新（upsert），类型 2 是批量删除。序列号必须从 1 开始并保持连续。恢复时只能截断不完整或校验和无效的最后一帧。

## 分段二进制对象

每个 `.bin` 文件都独立成帧：

```text
magic "MQSG" (4)
format version (1)
JSON payload length (4)
canonical JSON payload (N)
CRC32 of header plus payload (4)
```

`meta.json` 记录模式、是否已索引的标志，以及每个二进制对象的 SHA-256。点 ID 会被明确标记为整数或 UUID。版本和墓碑（tombstone）是相互独立的逻辑列。当前实现在打开时会从这一语义映像重建内存索引。

## 快照

```text
snapshot/
├── snapshot.json
└── collection/
```

`snapshot.json` 将集合中的每个相对文件映射到 SHA-256。创建流程会把当前清单、其引用的分段、元数据、`CURRENT` 和 WAL 复制到临时根目录，执行 fsync，然后重命名。恢复流程会检查精确的文件集合和哈希值，验证清单与分段，复制到暂存集合，仅在请求时重写集合名称，成功打开该集合，然后将其发布。
