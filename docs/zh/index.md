# MiniQdrant 教程

> [English](../index.md) · 中文快速开始

MiniQdrant 是一个直接 API 优先的 Python 参考实现，覆盖过滤向量搜索、版本化
不可变分段、在线优化与持久恢复。它揭示单节点向量数据库的机制，不复刻 Qdrant
的网络 API 或分布式部署表面。

English summary: MiniQdrant makes single-node vector database mechanisms
inspectable without claiming Qdrant API or deployment compatibility.

## 安装

```bash
git clone https://github.com/system-in-miniature/MiniQdrant.git
cd MiniQdrant
uv sync
```

需要 Python 3.12+ 与 [uv](https://docs.astral.sh/uv/)。

## 第一个实验

```bash
uv run python -m miniqdrant.labs.filtering
```

实验在一个小集合上带租户过滤搜索，输出命中 ID `[1, 3]`：另一个向量相似但
租户不同的点被排除，同时还会暴露所选的分段内查询计划。

接着阅读[架构总览](ARCHITECTURE.md)，再把模块逐项映射到
[Qdrant](qdrant-mapping.md)。完整 API、CLI、范围和可靠性边界见
[仓库中文 README](https://github.com/system-in-miniature/MiniQdrant/blob/main/README.zh-CN.md)。
