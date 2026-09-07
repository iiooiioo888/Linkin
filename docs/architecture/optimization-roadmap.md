# 性能优化路线图

本文档记录 EvoLoop 性能与成本优化的优先级、实现状态与配置项。

## 优先级总览

| 优先级 | 优化项 | 预期收益 | 状态 |
|--------|--------|----------|------|
| **P0** | 任务-模型匹配（不同环节用不同规模模型） | 成本降低 40–60% | ✅ 已实现 |
| **P0** | 反思早停机制 | 避免无效调用，延迟降低 | ✅ 已实现 |
| **P1** | 模型池健康检查 + 自动降级 | 主模型超时/限流自动切换 | ✅ 已实现 |
| **P1** | 成本感知路由 | 简单任务走便宜模型 | ✅ 已实现 |
| **P1** | Reviewer + Synthesizer 合并 | 延迟降低 ~25% | ✅ 已实现 |
| **P1** | 分层缓存 | 命中率提升 | ✅ 已实现 |
| **P2** | 路由自适应反馈 | 长期质量提升 | ✅ 已实现 |
| **P2** | 邊緣快取層 | 相似請求延遲可控 | ✅ 已实现 |
| **P3** | 可观测性全链路 trace | 为后续优化提供数据基础 | ✅ 已实现 |
| **P3** | 动态反思阈值 | 简单任务减少过度反思 | ✅ 已实现 |
| **P3** | 用户反馈闭环 | 驱动策略自适应 | ✅ 已实现 |
| **P3** | Docker 资源限制 | 部署环境稳定性 | ✅ 已实现 |

---

## P0：任务-模型匹配

**模块**：`backend/core/stage_router.py`

反思闭环各环节自动选择不同 `BudgetTier`：

| 环节 | 默认 Tier | 说明 |
|------|-----------|------|
| generate / improve | ROUTINE | 日常生成 |
| evaluate / cross_eval | SUMMARY | 最便宜，适合评分 |
| reflect | REASONING | 根因分析需较强推理 |

**环境变量**（可选覆盖）：

```env
EVOL_STAGE_TIER_GENERATE=routine
EVOL_STAGE_TIER_EVALUATE=summary
EVOL_STAGE_TIER_REFLECT=reasoning
EVOL_STAGE_TIER_IMPROVE=routine
```

公司运行时工作项级别路由见 `backend/company/budget.py` → `TierRouter`。

---

## P0：反思早停

**模块**：`backend/core/graph.py` → `should_improve`

终止条件（任一满足即 finalize）：

1. 分数 ≥ `EVOL_PASS_THRESHOLD`（默认 8）
2. 迭代次数 ≥ `EVOL_MAX_ITERATIONS`（默认 3）
3. 分数提升 < `EVOL_MIN_SCORE_IMPROVEMENT`（默认 0.5）

详见 [reflection-loop.md](./reflection-loop.md)。

---

## P1：模型池健康检查 + 自动降级

**模块**：`backend/core/provider_pool.py` → `invoke_with_pool_failover`；`backend/core/llm.py` → `call_llm`

当主模型超时、限流或连续失败时，自动在 `allowed_models` 池内切换成本更低的备援模型（Hub 路由已有类似能力，此优化覆盖反思闭环主链路）。

```env
EVOL_LLM_POOL_FAILOVER=true          # 默认开启
EVOL_LLM_FAILOVER_TIMEOUT=30       # 单模型尝试超时（秒）
EVOL_LLM_FAILOVER_SLOW_S=10        # 慢调用视为失败
EVOL_LLM_POOL_FAIL_THRESHOLD=2     # 连续失败次数触发熔断
EVOL_LLM_POOL_OPEN_SEC=60          # 熔断持续时间
```

监控：`GET /monitor/llm-ops` → `ops.pool_failover`；系统指标 roadmap 项 `pool_failover`。

---

## P1：成本感知路由

**模块**：`backend/core/cost_speed_router.py` · 配置 `backend/config/cost_speed.json`

依任务复杂度（simple / medium / complex）与管线环节选择模型，并由 `route_by_complexity` 决定走单次生成或公司运行时：

| 复杂度 | 路径 | 典型模型 |
|--------|------|----------|
| simple | 单次生成 | qwen-turbo |
| medium | 单次生成 | qwen-plus |
| complex | 公司运行时 | deepseek-v4-pro |

```env
EVOL_COST_SPEED_ENABLED=true
EVOL_COST_SPEED_PATH=backend/config/cost_speed.json
```

热重载：`POST /config/cost-speed/reload`（修改配置后无需重启）

监控：`GET /monitor/optimization` → `cost_speed`

---

## P1：Reviewer + Synthesizer 合并

**模块**：`backend/company/orchestrator.py` → `_review_and_synthesize`

公司运行时阶段 3 默认启用合并模式：单次 LLM 完成交付物审查 + 整合，减少一次 API 往返。

```env
EVOL_MERGE_REVIEW_SYNTH=true   # 默认 true；设为 false 恢复分离流程
```

---

## P1：分层缓存

| 层级 | 模块 | 说明 |
|------|------|------|
| LLM 精确 + 语义 | `backend/core/llm_cache.py` | 反思循环 prompt 复用 |
| Hub 语义 | `backend/hub/cache.py` | AI Hub 对话缓存 |
| 任务拆分 | `backend/company/decomposer.py` | 分解结果 LRU |

```env
EVOL_LLM_CACHE_SIZE=512
EVOL_SEMANTIC_CACHE=true
EVOL_SEMANTIC_THRESHOLD=0.92
EVOL_DECOMPOSE_CACHE_SIZE=64
```

---

## P2：路由自适应反馈

**模块**：`backend/core/routing_feedback.py`

`route_by_complexity` 根据历史 simple/company 路由结果与最终分数，动态调整复杂任务字数门槛。

- simple 路由低分（<6）多次 → 提高门槛，更早走 company
- company 路由高分且 query 短 → 略降门槛

数据存储：`backend/data/routing_feedback.json`

```env
EVOL_ROUTING_FEEDBACK_PATH=backend/data/routing_feedback.json
EVOL_ROUTING_LENGTH_BIAS=0
```

---

## P2：邊緣快取層

監控中心「運行指標」彙總的是 **EvoLoop 自身運行狀態**（快取命中率、反思輪次、路由門檻、Trace、任務成功率等），**不是** OPC UA 工業現場感測。

- **前端**：`SystemMetricsPanel`（分頁鍵 `metrics`）· `GET /monitor/optimization`
- **工業 OPC 任務路徑**（閥位、馬達等感測標籤）僅在 `resolved_path === 'opc'` 時由 `opc_service` 處理，與監控中心系統指標無關

### 系統分層快取（監控 API）

**模組**：`backend/services/optimization_monitor.py` → `_layered_cache_status()`

反映 `backend/core/llm_cache.py` 精確 + 語義快取條目數與命中率，供 `GET /monitor/optimization` 與「運行指標」分頁使用。

```env
EVOL_LLM_CACHE_SIZE=512
EVOL_LLM_CACHE_TTL=3600
EVOL_SEMANTIC_CACHE=true
EVOL_SEMANTIC_THRESHOLD=0.92
```

### OPC 工業邊緣快取（僅工業任務路徑）

**模組**：`opc_service/sense.py`

僅在 `route_by_complexity` 走 OPC 6 級閉環時使用，與運行指標監控無關。

| 模式 | 行為 |
|------|------|
| `auto` | 邊緣快取 TTL 內復用，否則雲拉取 |
| `edge` | 僅使用本地快取 |
| `cloud` | 始終 HTTP 拉取 OPC 微服務 |

```env
EVOL_OPC_TIER=auto
EVOL_OPC_EDGE_TTL=5
EVOL_OPC_EDGE_CACHE=opc_service/data/edge_cache.json
```

---

## P3：全链路 trace

**模块**：

  - `backend/services/trace_logger.py` — 任务级 JSONL 轨迹；`aggregate_reflection_stats()` 彙總反思輪次/耗時/改進幅度
- `backend/core/pipeline_trace.py` — LangGraph 节点事件

节点在 `session_id` / `task_id` 存在时自动写入 trace，供监控面板与后续分析使用。

监控：`GET /monitor/optimization` → `reflection_trace`（均轮次、均改进幅度、最近任务链路表）；「系统指标」分页展示。

---

## P3：动态反思阈值

**模块**：`backend/core/dynamic_threshold.py`

依任务复杂度与用户满意度自适应调整 `EVOL_PASS_THRESHOLD`：

| 场景 | 行为 |
|------|------|
| 短查询（< 80 字）且无复杂关键词 | 门槛降低（默认 -0.5） |
| 长查询或含开发/架构关键词 | 门槛提高（默认 +0.3） |
| simple 路由历史低分率高 | 略提高门槛 |
| 用户满意度低 | 略提高门槛 |

```env
EVOL_PASS_THRESHOLD=8
EVOL_THRESHOLD_SIMPLE_BIAS=-0.5
EVOL_THRESHOLD_COMPLEX_BIAS=0.3
EVOL_THRESHOLD_MIN=6.5
EVOL_THRESHOLD_MAX=9.0
```

---

## P3：用户反馈闭环

**模块**：`backend/core/user_feedback.py`

- `POST /feedback` — 收集 thumbs_up / thumbs_down / copy / edit
- `GET /feedback/stats` — 满意度统计
- 反馈数据影响动态阈值微调

```env
EVOL_USER_FEEDBACK_PATH=backend/data/user_feedback.json
EVOL_USER_FEEDBACK_MAX=500
```

---

## P3：Docker 资源限制

**文件**：`docker-compose.yml`

各服务已配置 `deploy.resources.limits`（CPU / 内存），避免容器争抢导致性能波动。

---

## 相关文档

- [反思闭环](./reflection-loop.md)
- [公司运行时](./company-runtime.md)
- [OPC 整合](./opc-integration.md)
