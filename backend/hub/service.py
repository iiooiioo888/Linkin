"""同步推論與 Agent 任務編排。只透過 backend.core.llm.call_llm 發模型請求。"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

from backend.core.llm import call_llm
from backend.hub.budget_guard import actual_cost_usd, estimate_cost_usd, estimate_tokens
from backend.hub.cache import semantic_key, should_bypass_cache
from backend.hub.catalog import (
    ALLOWED_STRATEGIES,
    ALLOWED_TOOLS,
    HUB_CATALOG,
    QUALITY_FLAGSHIP,
    is_forbidden_model_string,
    provider_of,
    runtime_hub_whitelist,
    validate_model_id,
)
from backend.hub.errors import (
    MSG_ALL_DOWN,
    MSG_BUDGET,
    MSG_EGRESS,
    MSG_FAILOVER_OK,
    MSG_FILTER,
    MSG_TIMEOUT,
    MSG_UNSUPPORTED,
    HubError,
)
from backend.hub.router import (
    CONNECT_TIMEOUT_S,
    HubUpstreamError,
    Metrics,
    agent_synthesis_chain,
    default_metrics,
    invoke_with_failover,
    pick_primary,
    race_sync,
    race_to_the_top,
)
from backend.hub.runtime import runtime
from backend.hub.safety import contains_sensitive, content_is_multimodal, flatten_messages_text
from backend.hub.store import AgentTask, HubUser, new_chat_id, new_task_id, new_trace_id
from backend.hub.tools import infer_tools, invoke_tool, tool_arguments


def _record_circuit(model: str, failed: bool, duration_s: float) -> None:
    runtime.circuits.get(model).record(failed, duration_s=duration_s)


def _llm_probe(prompt: str, system: str | None, model: str, **kwargs: Any) -> str:
    runtime.upstream_calls.append({"model": model, "prompt": prompt[:80]})
    return call_llm(prompt, system=system, model=model, **kwargs)


def parse_failover_config(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {
            "connect_timeout_ms": 25000,
            "read_timeout_ms": 120000,
            "max_retries": 3,
            "backoff_base": 2,
            "model_whitelist": None,
            "enable_race": False,
        }
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HubError(400, "BAD_REQUEST", "x-failover-config 不是合法 JSON") from exc
    if not isinstance(data, dict):
        raise HubError(400, "BAD_REQUEST", "x-failover-config 必須為物件")
    whitelist = data.get("model_whitelist")
    if whitelist is not None:
        if not isinstance(whitelist, list) or not (1 <= len(whitelist) <= 8):
            raise HubError(400, "BAD_REQUEST", "model_whitelist 長度須 1–8")
        cleaned: list[str] = []
        for item in whitelist:
            if not isinstance(item, str) or is_forbidden_model_string(item) or item not in HUB_CATALOG:
                raise HubError(400, "UNSUPPORTED_MODEL", MSG_UNSUPPORTED)
            cleaned.append(item)
        data["model_whitelist"] = cleaned
    data.setdefault("connect_timeout_ms", 25000)
    data.setdefault("read_timeout_ms", 120000)
    data.setdefault("enable_race", False)
    return data


def _validate_messages(messages: Any) -> list[dict[str, Any]]:
    """驗證聊天消息列表，加強輸入驗證。
    
    驗證規則：
    - 必須是非空列表
    - 最多 200 則消息
    - 每則消息必須包含 role 和 content
    - role 必須在允許的枚舉值中
    - content 不能為空或過長（最大 8000 字符）
    - 防止 XSS 和注入攻擊
    """
    import re
    
    if not isinstance(messages, list) or len(messages) == 0:
        raise HubError(400, "EMPTY_MESSAGES", "messages 不可為空")
    if len(messages) > 200:
        raise HubError(400, "BAD_REQUEST", "messages 最多 200 則")
    
    # 危險字符模式（防止腳本注入）
    dangerous_patterns = re.compile(r'<script[^>]*>|javascript:|on\w+\s*=', re.IGNORECASE)
    
    cleaned: list[dict[str, Any]] = []
    for idx, msg in enumerate(messages):
        if not isinstance(msg, dict):
            raise HubError(400, "BAD_REQUEST", f"第 {idx+1} 則消息必須為物件")
        if "role" not in msg or "content" not in msg:
            raise HubError(400, "BAD_REQUEST", f"第 {idx+1} 則消息缺少 role 或 content")
        
        role = msg["role"]
        if not isinstance(role, str):
            raise HubError(400, "BAD_REQUEST", f"第 {idx+1} 則消息的 role 必須為字符串")
        if role not in {"system", "user", "assistant", "tool"}:
            raise HubError(400, "BAD_REQUEST", f"第 {idx+1} 則消息的 role 不在允許範圍")
        
        content = msg["content"]
        if not isinstance(content, (str, list)):
            raise HubError(400, "BAD_REQUEST", f"第 {idx+1} 則消息的 content 格式錯誤")
        
        if isinstance(content, str):
            if not content.strip():
                raise HubError(400, "BLANK_CONTENT", f"第 {idx+1} 則消息的 content 不可全空白")
            if len(content) > 8000:
                raise HubError(400, "CONTENT_TOO_LONG", f"第 {idx+1} 則消息的 content 超過 8000 字符")
            # 檢查危險內容
            if dangerous_patterns.search(content):
                raise HubError(400, "DANGEROUS_CONTENT", f"第 {idx+1} 則消息包含不安全的內容")
        elif isinstance(content, list):
            # 多模態內容驗證
            if len(content) > 20:
                raise HubError(400, "BAD_REQUEST", f"第 {idx+1} 則消息的多模態內容過多")
            for item in content:
                if not isinstance(item, dict):
                    raise HubError(400, "BAD_REQUEST", f"第 {idx+1} 則消息的多模態項目必須為物件")
        
        cleaned.append({"role": role, "content": content})
    return cleaned


def complete_chat(
    user: HubUser,
    body: dict[str, Any],
    *,
    strategy: str,
    region: str,
    failover_raw: str | None,
    request_id: str,
    sleeper: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    if strategy not in ALLOWED_STRATEGIES:
        raise HubError(400, "BAD_REQUEST", "x-routing-strategy 枚舉不合法")

    messages = _validate_messages(body.get("messages"))
    temperature = float(body.get("temperature", 0.7))
    if not 0.0 <= temperature <= 2.0:
        raise HubError(400, "BAD_REQUEST", "temperature 須在 0–2")
    max_tokens = int(body.get("max_tokens") or 2048)
    if not 1 <= max_tokens <= 32768:
        raise HubError(400, "BAD_REQUEST", "max_tokens 超出範圍")
    stream = bool(body.get("stream", False))
    session_id = ""
    meta = body.get("metadata") or {}
    if isinstance(meta, dict):
        session_id = str(meta.get("session_id") or "")
    session_id = session_id or str(body.get("user") or "")

    raw_model = body.get("model")
    if raw_model is not None and not isinstance(raw_model, str):
        raise HubError(400, "UNSUPPORTED_MODEL", MSG_UNSUPPORTED)
    try:
        model = validate_model_id(raw_model)
    except ValueError as exc:
        raise HubError(400, "UNSUPPORTED_MODEL", MSG_UNSUPPORTED) from exc

    failover = parse_failover_config(failover_raw)
    whitelist = failover.get("model_whitelist") or runtime_hub_whitelist()
    if model and whitelist and model not in whitelist:
        model = whitelist[0]
    multimodal = content_is_multimodal(messages)
    if multimodal and region.upper() == "CN":
        raise HubError(400, "MODALITY_NOT_ALLOWED_IN_REGION", MSG_EGRESS)

    metrics = {
        m: Metrics(
            latency_ms=float(row.get("latency_ewma_ms") or default_metrics(m).latency_ms),
            price_out_per_1m=float(row.get("price_out_per_1m") or default_metrics(m).price_out_per_1m),
        )
        for m, row in runtime.store.provider_metrics.items()
        if m in HUB_CATALOG
    }

    try:
        decision = pick_primary(
            strategy=strategy,
            region=region,
            whitelist=whitelist,
            metrics_by_model=metrics,
            manual_model=model,
            circuit_open=runtime.circuits.is_open,
        )
    except PermissionError as exc:
        raise HubError(403, "DATA_EGRESS_FORBIDDEN", MSG_EGRESS) from exc
    except ValueError as exc:
        raise HubError(400, "BAD_REQUEST", "manual 策略必須提供 model") from exc

    if multimodal and decision.model != "gemini-3.1-pro":
        if region.upper() == "CN":
            raise HubError(400, "MODALITY_NOT_ALLOWED_IN_REGION", MSG_EGRESS)
        decision.model = "gemini-3.1-pro"
        decision.provider = provider_of("gemini-3.1-pro")
        decision.reason = "multimodal"

    prompt_text = flatten_messages_text(messages)
    input_tokens = estimate_tokens(prompt_text)
    estimate = estimate_cost_usd(decision.model, input_tokens, max_tokens)
    if runtime.budget.would_exceed(str(user.id), estimate, user.daily_budget_limit_usd):
        runtime.store.append_log(
            {
                "id": new_chat_id(),
                "user_id": str(user.id),
                "provider": "none",
                "model_name": decision.model,
                "status": "budget_denied",
                "cost_usd": 0.0,
                "error_code": "BUDGET_EXCEEDED",
            }
        )
        raise HubError(403, "BUDGET_EXCEEDED", MSG_BUDGET)

    bypass = should_bypass_cache(temperature, stream, multimodal)
    cache_status = "BYPASS"
    chat_id = new_chat_id()
    trace_id = request_id.replace("-", "")[:32].ljust(32, "0") if request_id else new_trace_id()
    t0 = time.monotonic()
    hops = 0
    text = ""
    used_model = decision.model
    notice = ""

    if not bypass:
        key = semantic_key(str(user.id), strategy, messages)
        cached = runtime.cache.get(key)
        if cached:
            cache_status = "HIT"
            cached = dict(cached)
            cached["id"] = chat_id
            cached["cost_usd"] = 0.0
            cached["cache"] = "HIT"
            cached["chosen_provider"] = "cache"
            runtime.store.append_log(
                {
                    "id": chat_id,
                    "user_id": str(user.id),
                    "session_id": session_id,
                    "provider": "cache",
                    "model_name": "semantic-cache",
                    "status": "success",
                    "cost_usd": 0.0,
                    "latency_ms": int((time.monotonic() - t0) * 1000),
                    "trace_id": trace_id,
                }
            )
            return cached
        cache_status = "MISS"

    connect_s = float(failover.get("connect_timeout_ms", 25000)) / 1000.0
    read_s = float(failover.get("read_timeout_ms", 120000)) / 1000.0
    connect_s = min(max(connect_s, 1.0), CONNECT_TIMEOUT_S * 3)
    read_s = min(max(read_s, 1.0), 180.0)

    enable_race = bool(failover.get("enable_race")) or strategy == "speed_first"
    raced = False
    if enable_race and region.upper() != "CN" and not multimodal:
        try:
            used_model, text = race_sync(_llm_probe, messages)
            raced = True
        except TimeoutError:
            raced = False
            text = ""

    if not text:
        try:
            text, used_model, hops = invoke_with_failover(
                _llm_probe,
                messages,
                decision.model,
                region,
                whitelist,
                connect_s=connect_s,
                read_s=read_s,
                sleeper=sleeper or (lambda _s: None),
                circuit_open=runtime.circuits.is_open,
                on_result=_record_circuit,
            )
        except TimeoutError as exc:
            raise HubError(504, "UPSTREAM_TIMEOUT", MSG_TIMEOUT) from exc
        except HubUpstreamError as exc:
            raise HubError(503, "ALL_PROVIDERS_UNAVAILABLE", MSG_ALL_DOWN) from exc

    latency_ms = int((time.monotonic() - t0) * 1000)
    if contains_sensitive(text):
        runtime.store.append_log(
            {
                "id": chat_id,
                "user_id": str(user.id),
                "session_id": session_id,
                "provider": provider_of(used_model) if used_model in HUB_CATALOG else "unknown",
                "model_name": used_model,
                "status": "filtered",
                "cost_usd": 0.0,
                "error_code": "CONTENT_FILTER",
                "trace_id": trace_id,
            }
        )
        raise HubError(400, "CONTENT_FILTER", MSG_FILTER)

    out_tokens = estimate_tokens(text)
    cost = actual_cost_usd(used_model, input_tokens, out_tokens)
    runtime.budget.add(str(user.id), cost)
    if hops > 0:
        notice = MSG_FAILOVER_OK

    payload = {
        "id": chat_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": used_model,
        "chosen_provider": provider_of(used_model),
        "cost_usd": round(cost, 6),
        "latency_ms": latency_ms,
        "routing_strategy": strategy,
        "failover_hops": hops,
        "cache": cache_status,
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": text},
            }
        ],
        "usage": {
            "prompt_tokens": input_tokens,
            "completion_tokens": out_tokens,
            "total_tokens": input_tokens + out_tokens,
        },
    }
    if notice:
        payload["notice"] = notice
    if raced:
        payload["race"] = True

    if not bypass:
        runtime.cache.set(semantic_key(str(user.id), strategy, messages), payload)

    runtime.store.append_log(
        {
            "id": chat_id,
            "user_id": str(user.id),
            "session_id": session_id,
            "provider": payload["chosen_provider"],
            "model_name": used_model,
            "prompt_tokens": input_tokens,
            "completion_tokens": out_tokens,
            "cost_usd": cost,
            "status": "success",
            "latency_ms": latency_ms,
            "trace_id": trace_id,
        }
    )
    return payload


async def race_first_token(stream_factory) -> tuple[str, bytes]:
    return await race_to_the_top(stream_factory)


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


def authenticate(authorization: str | None) -> HubUser:
    """驗證 Bearer Token。
    
    支援兩種認證方式：
    1. API Key: Bearer <api_key> - 從 store 中查找匹配的用戶
    2. JWT Token: Bearer <jwt_token> - 驗證 JWT 簽名和過期時間
    
    增強驗證邏輯：
    - 嚴格檢查 Authorization header 格式
    - 防止空白或過短的 token
    - 對 JWT token 進行完整的簽名和過期驗證
    """
    import base64
    import hashlib
    import hmac
    import json
    import time
    
    if not authorization:
        raise HubError(401, "UNAUTHORIZED", "缺少 Authorization header")
    
    if not authorization.startswith("Bearer "):
        raise HubError(401, "UNAUTHORIZED", "Authorization header 必須以 Bearer 開頭")
    
    token = authorization[7:].strip()
    
    if not token or len(token) < 10:
        raise HubError(401, "UNAUTHORIZED", "Token 長度不足")
    
    # 檢查是否為 JWT token (包含三個部分，以 . 分隔)
    if token.count(".") == 2:
        # JWT token 驗證
        try:
            header_b, body_b, sig_b = token.split(".")
            
            # 填充 base64url
            pad = "=" * (-len(body_b) % 4)
            header_pad = "=" * (-len(header_b) % 4)
            
            # 解碼 payload 獲取過期時間
            try:
                payload = json.loads(base64.urlsafe_b64decode(body_b + pad))
            except Exception as exc:
                raise HubError(401, "UNAUTHORIZED", "JWT payload 解析失敗") from exc
            
            # 驗證過期時間
            now = int(time.time())
            exp = payload.get("exp", 0)
            iat = payload.get("iat", 0)
            
            if exp and exp < now:
                raise HubError(401, "UNAUTHORIZED", "JWT token 已過期")
            
            if iat and (now - iat) > 86400:  # 超過 24 小時
                raise HubError(401, "UNAUTHORIZED", "JWT token 簽發時間過久")
            
            # 驗證簽名
            from backend.hub.tools import JWT_SECRET
            expected_sig = base64.urlsafe_b64encode(
                hmac.new(JWT_SECRET, f"{header_b}.{body_b}".encode(), hashlib.sha256).digest()
            ).rstrip(b"=").decode("ascii")
            
            if not hmac.compare_digest(expected_sig, sig_b):
                raise HubError(401, "UNAUTHORIZED", "JWT 簽名驗證失敗")
            
            # 從 JWT 中提取用戶 ID
            user_id = payload.get("sub")
            if not user_id:
                raise HubError(401, "UNAUTHORIZED", "JWT 缺少用戶標識")
            
            # 創建臨時用戶對象（實際應用中應從數據庫加載）
            from uuid import UUID
            user = HubUser(
                id=UUID(user_id) if isinstance(user_id, str) else user_id,
                name=payload.get("name", "jwt-user"),
                api_key_hash="",
                daily_budget_limit_usd=payload.get("daily_budget", 10.0),
            )
            return user
            
        except HubError:
            raise
        except Exception as exc:
            raise HubError(401, "UNAUTHORIZED", f"JWT 驗證失敗：{exc}") from exc
    
    # API Key 驗證（原有邏輯）
    if not (43 <= len(token) <= 128):
        # 開發金鑰較短時仍允許精確命中 store
        short_key_user = runtime.store.get_by_api_key(token)
        if short_key_user:
            return short_key_user
        raise HubError(401, "UNAUTHORIZED", "缺少或無效的 API Key")
    
    api_user = runtime.store.get_by_api_key(token)
    if api_user is None:
        raise HubError(401, "UNAUTHORIZED", "缺少或無效的 API Key")
    return api_user
