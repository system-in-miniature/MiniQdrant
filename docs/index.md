# MiniQdrant Tutorial / MiniQdrant 教程

> English quick start / 英文快速开始 · [Chinese edition / 中文版](zh/index.md)

MiniQdrant is a direct-first Python reference implementation of filtered
vector search, versioned immutable segments, online optimization, and durable
recovery. It exposes the mechanisms behind a single-node vector database
without reproducing Qdrant's network API or distributed deployment surface.

MiniQdrant 是一个直接 API 优先的 Python 参考实现，覆盖过滤向量搜索、版本化
不可变分段、在线优化与持久恢复。它揭示单节点向量数据库的机制，不复刻 Qdrant
的网络 API 或分布式部署表面。

## Install / 安装

```bash
git clone https://github.com/system-in-miniature/MiniQdrant.git
cd MiniQdrant
uv sync
```

Python 3.12+ and [uv](https://docs.astral.sh/uv/) are required.

需要 Python 3.12+ 与 [uv](https://docs.astral.sh/uv/)。

## First experiment / 第一个实验

```bash
uv run python -m miniqdrant.labs.filtering
```

The lab searches a tiny collection with a tenant filter. It prints matching
IDs `[1, 3]`, excluding a vector-similar point from another tenant, and exposes
the selected per-segment plan.

实验在一个小集合上带租户过滤搜索，输出命中 ID `[1, 3]`：另一个向量相似但
租户不同的点被排除，同时还会暴露所选的分段内查询计划。

Continue with the [architecture tour](architecture.md), then compare modules
with [Qdrant](qdrant-mapping.md).

接着阅读[架构总览](architecture.md)，再把模块逐项映射到
[Qdrant](qdrant-mapping.md)。

For the complete API, CLI, scope, and reliability boundary, read the
[repository README](https://github.com/system-in-miniature/MiniQdrant/blob/main/README.md).

完整 API、CLI、范围和可靠性边界见
[仓库中文 README](https://github.com/system-in-miniature/MiniQdrant/blob/main/README.zh-CN.md)。
