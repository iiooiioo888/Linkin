# FEATURES_AND_TOOLS — 范围与 backlog 指针

功能矩阵与工具选型的**权威原文**在仓库根目录：

- [`FEATURES_AND_TOOLS.md`](../../FEATURES_AND_TOOLS.md)（§0–5）
- 规格：[`PROJECT_SPEC.md`](../../PROJECT_SPEC.md)
- 已合入 MVP：[#167](https://github.com/iiooiioo888/Linkin/pull/167)

## Backlog

§4 拆出的 GitHub-style issues：[`docs/backlog/`](../backlog/README.md)

| 状态 | 含义 |
|---|---|
| done | #167 已满足 §1 验收（代码+测试） |
| done* | 模板／路径已合入；真机 GPU 属运维验收 |
| partial | 有骨架，仍有明确 gap |
| gap | §1 P0 尚未落地 |
| open / stub | P1 |

## 原则（摘录）

1. 功能与工具解耦；验收不绑定具体工具名。  
2. MVP 只做 P0；P1 留接口；P2 只写文档。  
3. §2.4「明确不引入」不得加入依赖（Celery／K8s／MinIO／向量库等）。

相关：[`local-video-studio.md`](./local-video-studio.md) · [`OPERATIONS.md`](./OPERATIONS.md)
