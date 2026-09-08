# AGENTS.md — EvoLoop

## 项目概述

EvoLoop 是一个具备自我反思闭环的**统一模式** AI 助手系统。核心架构基于 **LangGraph 统一管线**，将三大能力融合在同一条管线中：

- **反思闭环**（生成 → 评估 → 反思 → 优化）：所有产出一律进入评估/反思/改进迭代回路，确保最终交付品质达标
- **公司运行时**（L5 用户 Grill-Me → L4 战役 DAG → L3 原子拆解 → L2 专注执行 → L1 宪兵审查 → Reviewer 审查 → Synthesizer 整合）：复杂任务自动触发，由递归因对抗分层组织（RAHO）制衡后分工完成
- **OPC 整合**（感知 → 预处理 → 分析 → 诊断 → 决策 → 执行）：工业任务自动注入感测数据上下文，实现工业感知-诊断-行动闭环

系统不再区分"标准/公司/OPC"三种模式，而是由 `route_by_complexity` 节点依任务内容自动判断执行路径（简单任务 → 单次生成；复杂任务 → 公司运行时；工业任务 → OPC 6 级闭环）。

## 模块边界与职责

| 模块 | 路径 | 职责 |
| --- | --- | --- |
| 图定义 | `backend/core/` | LangGraph 反思闭环、LiteLLM 调用层（`llm.py`）、多 API 路由（`api_router.py`）、模型池锁定、EvoLoopState |
| 公司运行时 | `backend/company/` | 多代理人协调器、RAHO（`company/raho/`）、角色定义、工作项状态机与依赖 DAG、预算控制与模型路由、Prompt 模板 |
| Minecraft MCP | `backend/tools/` + `backend/linkin/minecraft.py` | MineMCP JSON-RPC 封装、铁律、审计；角色经 tool_registry 调用 |
| OPC 微服务 | `opc_service/` | OPC UA 工业数据读写与订阅、安全护栏（白名单/边界检查/审计日志）、模拟 OPC 服务器 |

## 关键约束

1. **LLM 调用层**：统一使用 LiteLLM 作为 LLM 调用抽象层，所有节点必须通过 `backend.core.llm.call_llm` 调用 LLM，**禁止**直接调用任何模型供应商的 SDK。
2. **测试隔离**：单元测试使用 `monkeypatch` 隔离 LLM 调用与外部服务依赖（ChromaDB、Redis、OPC UA、Minecraft MCP），无需真实 API 密钥或游戏伺服器即可运行。
3. **图状态不可直接修改**：编译后的 LangGraph 图状态（`evoloop_graph`）为运行时产物，**禁止**直接修改，所有变更应通过修改 `build_graph()` 函数和节点实现完成。
4. **OPC 安全护栏**：所有 OPC 写操作必须经过 `opc_service/guard.py` 安全护栏检查（白名单验证、数值边界检查），**禁止**绕过护栏直接写入 OPC 标签。
5. **Minecraft MCP**：所有对游戏世界的写操作必须经过 `backend/tools/minecraft_mcp.py` 与 `backend/linkin/minecraft.py`（允许清单、命令链、敏感二次确认、fill 体积上限）。**禁止**让节点或角色直连 MineMCP，也禁止把 `write_file` 等文件系统工具暴露给角色。

## 常用命令

```powershell
# 运行全部测试
pytest backend/tests/

# 运行特定模块测试
pytest backend/tests/test_reflection_loop.py
pytest backend/tests/test_company.py
pytest backend/tests/test_opc_service.py
pytest backend/tests/test_linkin_api.py
pytest backend/tests/test_minecraft_mcp.py

# Docker Compose 启动全部服务
docker compose up -d

# 仅启动基础设施（Redis + ChromaDB）
docker compose up -d redis chroma

# 启动后端 API（FastAPI + LangGraph）
python -m backend.main

# 前端开发（默认 http://localhost:3001）
cd frontend; npm run dev

# 示范 60 任务 / 60 推理 / 60 知识库
python -m backend.scripts.seed_demo_content

# 启动 OPC 微服务（含模拟服务器）
$env:OPC_SIM_ENABLED="true"; python -m opc_service.main

# 冒烟测试（向量记忆库）
python -m backend.scripts.smoke_test

# LLM 连线测试
python backend/scripts/test_llm_connection.py
```

## 禁止操作

以下为关键约束中禁止事项的快速索引：

- **禁止直接调用模型供应商 SDK** → 参见 [关键约束 #1](#关键约束)（LLM 调用层）
- **禁止直接修改编译后的 LangGraph 图状态** → 参见 [关键约束 #3](#关键约束)（图状态不可直接修改）
- **禁止绕过 OPC 安全护栏直接写入 OPC 标签** → 参见 [关键约束 #4](#关键约束)（OPC 安全护栏）
- **禁止绕过 Minecraft MCP 护栏或暴露文件系统工具** → 参见 [关键约束 #5](#关键约束)