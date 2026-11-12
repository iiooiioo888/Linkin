"""Hub agent task 建立／執行／查詢（自 backend.hub.service 抽出）。"""

from __future__ import annotations

import json
import time
from typing import Any

from backend.hub.budget_guard import (
    actual_cost_usd,
    estimate_cost_usd,
    estimate_tokens,
)
from backend.hub.catalog import (
    ALLOWED_TOOLS,
    QUALITY_FLAGSHIP,
    provider_of,
    runtime_hub_whitelist,
)
from backend.hub.errors import (
    MSG_ALL_DOWN,
    MSG_BUDGET,
    MSG_FILTER,
    HubError,
)
from backend.hub.router import (
    HubUpstreamError,
    agent_synthesis_chain,
    invoke_with_failover,
)
from backend.hub.runtime import runtime
from backend.hub.safety import contains_sensitive
from backend.hub.store import (
    AgentTask,
    HubUser,
    new_task_id,
    new_trace_id,
)
from backend.hub.tools import (
    infer_tools,
    invoke_tool,
    tool_arguments,
)

from .failover import parse_failover_config
from .probe import _llm_probe, _record_circuit


def create_agent_task(
    user: HubUser,
    body: dict[str, Any],
    *,
    strategy: str,
    region: str,
    failover_raw: str | None,
    idempotency_key: str | None,
    request_id: str,
) -> AgentTask:
    text = str(body.get("input") or "")
    if not (1 <= len(text) <= 8000):
        raise HubError(400, "BAD_REQUEST", "input 長度須 1–8000")
    tools = body.get("tools")
    if tools is None:
        tools = infer_tools(text)
    if not isinstance(tools, list) or len(tools) > 16:
        raise HubError(400, "BAD_REQUEST", "tools 最多 16 個")
    for name in tools:
        if name not in ALLOWED_TOOLS:
            raise HubError(400, "BAD_REQUEST", "tools 枚舉不合法")
        if name == "PysdnOPC_write":
            raise HubError(400, "OPC_GUARD_REQUIRED", "工業寫入被安全護欄拒絕。")

    if idempotency_key:
        existing = runtime.store.idempotency.get(f"{user.id}:{idempotency_key}")
        if existing and existing in runtime.store.tasks:
            return runtime.store.tasks[existing]

    task = AgentTask(
        task_id=new_task_id(),
        user_id=user.id,
        status="queued",
        input=text,
        tools=list(tools),
        trace_id=(request_id.replace("-", "")[:32].ljust(32, "0") if request_id else new_trace_id()),
        progress_pct=0,
    )
    runtime.store.tasks[task.task_id] = task
    if idempotency_key:
        runtime.store.idempotency[f"{user.id}:{idempotency_key}"] = task.task_id

    # 預算：Agent 以 (1+len(tools)) 取代額外 1.2，buffer 只乘一次
    input_tokens = estimate_tokens(text)
    primary = QUALITY_FLAGSHIP if region.upper() != "CN" else "deepseek-v4-flash"
    estimate = estimate_cost_usd(primary, input_tokens, 4096) * max(1, 1 + len(tools)) / 1.2
    if runtime.budget.would_exceed(str(user.id), estimate, user.daily_budget_limit_usd):
        task.status = "failed"
        task.error_code = "BUDGET_EXCEEDED"
        raise HubError(403, "BUDGET_EXCEEDED", MSG_BUDGET)

    run_agent_task(task, user, strategy=strategy, region=region, failover_raw=failover_raw)
    return task


def run_agent_task(
    task: AgentTask,
    user: HubUser,
    *,
    strategy: str,
    region: str,
    failover_raw: str | None,
) -> None:
    task.status = "running"
    task.progress_pct = 10
    t0 = time.monotonic()
    traces: list[dict[str, Any]] = []
    try:
        failover = parse_failover_config(failover_raw)
        whitelist = failover.get("model_whitelist") or runtime_hub_whitelist()
        chain = agent_synthesis_chain(region, whitelist)
        primary = chain[0] if chain else QUALITY_FLAGSHIP
        tool_list = ", ".join(task.tools) or "（無）"
        system = (
            "你是工具增強子代理。必須先依據工具結果再給結論，禁止臆造未提供的數據。"
            f"已掛載工具：{tool_list}。以下 tool 結果為唯一來源。"
        )
        plan_messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": task.input},
        ]
        try:
            invoke_with_failover(
                _llm_probe,
                plan_messages,
                primary,
                region,
                whitelist,
                chain=chain,
                sleeper=lambda _s: None,
                circuit_open=runtime.circuits.is_open,
                on_result=_record_circuit,
            )
        except (TimeoutError, HubUpstreamError, HubError):
            pass
        task.progress_pct = 25

        tool_blobs: list[str] = []
        tool_messages: list[dict[str, Any]] = []
        for idx, name in enumerate(task.tools):
            t_tool = time.monotonic()
            result = invoke_tool(name, task.input, str(user.id))
            traces.append(
                {
                    "tool": name,
                    "latency_ms": int((time.monotonic() - t_tool) * 1000),
                    "http_status": int(result.get("http_status") or 200),
                    "data": result.get("data"),
                }
            )
            blob = json.dumps(result.get("data"), ensure_ascii=False)
            tool_blobs.append(blob)
            call_id = f"call_{idx:04d}"
            arguments = result.get("arguments") or tool_arguments(name, task.input)
            tool_messages.append(
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": json.dumps(arguments, ensure_ascii=False),
                            },
                        }
                    ],
                }
            )
            tool_messages.append(
                {"role": "tool", "tool_call_id": call_id, "content": blob}
            )
        task.progress_pct = 55

        synth_messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": task.input},
            *tool_messages,
        ]
        if not tool_messages:
            synth_messages.append(
                {
                    "role": "user",
                    "content": f"使用者問題：{task.input}\n工具資料：（無）\n請給出投資建議。",
                }
            )
        text, used_model, hops = invoke_with_failover(
            _llm_probe,
            synth_messages,
            primary,
            region,
            whitelist,
            chain=chain,
            sleeper=lambda _s: None,
            circuit_open=runtime.circuits.is_open,
            on_result=_record_circuit,
        )
        if contains_sensitive(text):
            raise HubError(400, "CONTENT_FILTER", MSG_FILTER)
        user_msg = task.input + "".join(tool_blobs)
        cost = actual_cost_usd(used_model, estimate_tokens(user_msg), estimate_tokens(text))
        runtime.budget.add(str(user.id), cost)
        task.cost_usd = cost
        task.chosen_provider = provider_of(used_model)
        task.result = {
            "content": text,
            "model": used_model,
            "failover_hops": hops,
            "tool_traces": traces,
        }
        task.status = "succeeded"
        task.progress_pct = 100
    except HubError as exc:
        task.status = "failed"
        task.error_code = exc.code
        task.error_detail = exc.detail
        task.progress_pct = 100
        if exc.status >= 500:
            raise
    except (TimeoutError, HubUpstreamError) as exc:
        task.status = "failed"
        task.error_code = "ALL_PROVIDERS_UNAVAILABLE"
        task.error_detail = MSG_ALL_DOWN
        task.progress_pct = 100
        raise HubError(503, "ALL_PROVIDERS_UNAVAILABLE", MSG_ALL_DOWN) from exc
    finally:
        task.latency_ms = int((time.monotonic() - t0) * 1000)
        if task.status in {"succeeded", "failed"}:
            from datetime import datetime, timezone

            task.finished_at = datetime.now(timezone.utc)


def get_agent_task(user: HubUser, task_id: str) -> AgentTask:
    task = runtime.store.tasks.get(task_id)
    if task is None or task.user_id != user.id:
        raise HubError(404, "NOT_FOUND", "任務不存在")
    return task
