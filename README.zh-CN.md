> **Language**: [English](README.md) | 简体中文

# MiniQdrant

[![CI](https://github.com/system-in-miniature/mini-qdrant/actions/workflows/ci.yml/badge.svg)](https://github.com/system-in-miniature/mini-qdrant/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) ![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue.svg)

MiniQdrant 是一个直达机制优先（direct-first）的 Python 参考实现，涵盖过滤向量搜索、版本化不可变分段（immutable segment）、在线优化和持久恢复。它旨在揭示单节点向量数据库背后的机制，而不是复刻 Qdrant 的网络 API 或部署表面。

```text
validated mutation → WAL → mutable segment
                              ↓ flush
query → filter planner → immutable segments → version resolution → global Top-K
                              ↓ optimize
                  HNSW / scalar-quantized segment
```

## 已实现功能

- 支持固定维度的稠密向量，并提供余弦、点积或负平方欧几里得评分；
- 支持不可变 JSON 载荷（payload）、嵌套过滤器抽象语法树（filter AST）、载荷字段索引，以及按分段进行、感知基数的规划；
- 支持版本化的完整载荷替换、浅层字段合并和字段删除；
- 支持确定性的精确 Top-K 和 HNSW 候选搜索；
- 支持标量 int8 存储、对解码后的浮点候选进行评分、过采样，以及精确浮点重评分；
- 支持先写日志再应用（WAL-before-apply）的插入或更新（upsert）/删除操作、单调递增版本、墓碑（tombstone）、以清单（manifest）为恢复根的重启恢复，以及活动日志尾部修复；
- 支持在线合并、清理（vacuum）和索引重建、原子清单发布、稳定读取视图，以及通过引用计数清理过时分段；
- 支持带校验和、可移植的集合快照，以及替换前验证的恢复流程。

有意排除的功能列于 [DIFFERENCES_FROM_QDRANT.md](DIFFERENCES_FROM_QDRANT.md)。本项目与其未来课程有意保持独立。

## 快速开始

```bash
uv sync
uv run pytest -q
```

直接 API：

```python
from miniqdrant import Database, Distance, Point, SearchRequest

database = Database.open("./demo-data")
collection = database.create_collection(
    "items",
    dimension=3,
    distance=Distance.COSINE,
)
collection.upsert(
    [
        Point(1, (1, 0, 0), {"kind": "book"}),
        Point(2, (0, 1, 0), {"kind": "film"}),
    ]
)
result = collection.search(SearchRequest((1, 0, 0), limit=1))
assert result.hits[0].id == 1
database.close()
```

轻量命令行界面（CLI）：

```bash
uv run miniqdrant create ./demo-data items --dimension 3 --distance cosine
uv run miniqdrant upsert ./demo-data items ./points.jsonl
uv run miniqdrant search ./demo-data items '[1,0,0]' --limit 5
uv run miniqdrant payload-index ./demo-data items category keyword
uv run miniqdrant info ./demo-data items
uv run miniqdrant snapshot ./demo-data items ./snapshots/items-001
uv run miniqdrant restore ./snapshots/items-001 ./restored items
```

每个 JSONL 点都包含 `id`、`vector` 和可选的 `payload`。

## 阅读地图

- [ARCHITECTURE.md](docs/zh/ARCHITECTURE.md)：所有权、查询、变更、优化和恢复流程。
- [docs/behavior-matrix.md](docs/behavior-matrix.md)：从行为到测试的证据。
- [docs/qdrant-mapping.md](docs/zh/qdrant-mapping.md)：MiniQdrant 模块与最接近的 Qdrant 子系统及其语义关系的映射。
- [docs/storage-format.md](docs/zh/storage-format.md)：WAL、分段、清单和快照格式。
- [DIFFERENCES_FROM_QDRANT.md](docs/zh/DIFFERENCES_FROM_QDRANT.md)：精确的范围边界。
- [frozen design](docs/superpowers/specs/2026-07-27-miniqdrant-reference-project-design.md) 和 [implementation plan](docs/superpowers/plans/2026-07-27-miniqdrant-reference-project.md)。

## 可靠性边界

一项已确认的变更已经跨越所配置的预写日志持久性边界（WAL durability boundary）。在默认的 `always` 策略下，其帧会先执行 fsync，再应用到内存。发布清单后，新的不可变分段集合会通过 `CURRENT` 对重启恢复可见。搜索采用最大版本解析（greatest-version resolution），因此重放和暂时存在的跨分段重复记录具有幂等性。这是单进程参考运行时；它不对分布式一致性或副本确认作任何声明。

## 商标声明

MiniQdrant 是独立的教学项目，与 Qdrant Solutions GmbH 无隶属、背书或赞助关系。"Qdrant" 商标归其所有者所有。
