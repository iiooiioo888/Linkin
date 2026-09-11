"""LiteLLM 統一呼叫層（Task 0.3）。

負責模型設定、速率限制重試與回應解析，所有節點都透過
此模組呼叫 LLM，方便日後替換供應商或加入快取。

LLM 供應商參數（金鑰、端點、模型）優先讀取運行時
配置（llm_config，可透過 /config API 動態設定），
未設定時回退環境變數。
"""

import json
import logging
import re
import time

from dotenv import load_dotenv
from litellm import completion
from litellm.exceptions import APIError, RateLimitError

from backend.core.llm_cache import get_llm_cache
from backend.core.llm_config import get_runtime_config
from backend.core.provider_pool import (
    clamp_model,
    failover_models,
    invoke_with_pool_failover,
    pool_failover_enabled,
)

load_dotenv()

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2.0


def _llm_params(target: dict | None = None) -> dict:
    """讀取当前生效的 LLM 參數（每次呼叫時讀取，支援動態變更）。

    自訂 api_base 場景（如 Qwen 相容模式）：模型名必須帶
    `openai/` 供應商前綴，LiteLLM 才知道走 OpenAI 協定
    （未帶前綴的未知模型名會報 "LLM Provider NOT provided"），
    且 api_base 會覆蓋官方端點。
    """
    if target:
        params: dict = {"model": target.get("model") or "gpt-4o"}
        if target.get("api_key"):
            params["api_key"] = target["api_key"]
        if target.get("api_base"):
            params["api_base"] = target["api_base"]
            params["model"] = _ensure_provider_prefix(params["model"])
        return params
    cfg = get_runtime_config()
    params = {"model": cfg.get("model") or "gpt-4o"}
    if cfg.get("api_key"):
        params["api_key"] = cfg["api_key"]
    if cfg.get("api_base"):
        params["api_base"] = cfg["api_base"]
        params["model"] = _ensure_provider_prefix(params["model"])
    return params


def _resolve_call_target(model: str | None, route_id: str | None) -> dict:
    from backend.core.api_router import resolve_target

    return resolve_target(model=model, route_id=route_id)


def _truncate_prompt(prompt: str, max_context_tokens: int | None) -> str:
    """依角色上下文 Token 上限粗估截斷（約 4 字元 / token）。"""
    if not max_context_tokens or max_context_tokens <= 0:
        return prompt
    max_chars = max(256, int(max_context_tokens) * 4)
    if len(prompt) <= max_chars:
        return prompt
    keep = max_chars - 40
    return prompt[:keep] + "\n\n[...上下文已依角色 Token 上限截斷...]"


def _openrouter_extra(target: dict) -> dict:
    routing = target.get("provider_routing")
    if not isinstance(routing, dict) or not routing:
        return {}
    return {"extra_body": {"provider": routing}}


def _ensure_provider_prefix(model: str) -> str:
    """確保模型名帶供應商前綴；自訂端點場景補上 openai/。"""
    return model if "/" in model else f"openai/{model}"


_THINK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL | re.IGNORECASE)


def split_thinking(text: str | None) -> tuple[str, str]:
    """拆出思考過程與可見回答。"""
    raw = text or ""
    thoughts = [m.strip() for m in _THINK_RE.findall(raw) if m.strip()]
    rest = _THINK_RE.sub("", raw)
    open_m = re.search(r"<think>([\s\S]*)$", rest, re.IGNORECASE)
    if open_m:
        extra = open_m.group(1).strip()
        if extra:
            thoughts.append(extra)
        rest = rest[: open_m.start()]
    return "\n\n".join(thoughts).strip(), rest.strip()


def _delta_reasoning(delta: object | None) -> str:
    if delta is None:
        return ""
    return str(
        getattr(delta, "reasoning_content", None)
        or getattr(delta, "reasoning", None)
        or ""
    )


def _message_visible_text(message: object | None) -> str:
    """合併 reasoning_content 與 content，思考包在 <think> 內供前端拆分。"""
    if message is None:
        return ""
    content = getattr(message, "content", None) or ""
    reasoning = (
        getattr(message, "reasoning_content", None)
        or getattr(message, "reasoning", None)
        or ""
    )
    if reasoning and "<think>" not in str(content):
        return f"<think>{reasoning}</think>\n{content}"
    return str(content)


def _usage_tokens(response: object, *, prompt: str, system: str | None, output_text: str) -> tuple[int, int]:
    """從 LiteLLM 回應擷取 token 用量；缺省時以字元粗估。"""
    usage = getattr(response, "usage", None)
    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    if prompt_tokens <= 0:
        prompt_tokens = max(1, len(prompt) // 4 + len(system or "") // 4)
    if completion_tokens <= 0:
        completion_tokens = max(1, len(output_text) // 4)
    return prompt_tokens, completion_tokens


def _wallet_bill_llm(
    model: str,
    *,
    prompt: str,
    system: str | None,
    max_tokens: int | None,
    input_tokens: int,
    output_tokens: int,
    trace_label: str,
) -> None:
    from backend.billing.errors import FeatureNotEntitledError, InsufficientCreditsError
    from backend.billing.metering import meter_llm, precheck_llm

    try:
        if max_tokens and input_tokens <= 0:
            precheck_llm(model, max(1, len(prompt) // 4), int(max_tokens))
        else:
            precheck_llm(model, input_tokens, output_tokens)
        meter_llm(
            model,
            input_tokens,
            output_tokens,
            reference=trace_label or "call_llm",
            meta={"trace_label": trace_label or ""},
        )
    except (InsufficientCreditsError, FeatureNotEntitledError) as exc:
        raise RuntimeError(exc.message) from exc


def _completion_once(
    prompt: str,
    system: str | None = None,
    model: str | None = None,
    max_retries: int | None = None,
    *,
    route_id: str | None = None,
    max_context_tokens: int | None = None,
    trace_label: str = "",
    **kwargs,
) -> str:
    """單一模型 LLM 呼叫（含重試，不含池級 Failover）。"""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": _truncate_prompt(prompt, max_context_tokens)})

    try:
        target = _resolve_call_target(model, route_id)
    except Exception:
        target = None
    params = _llm_params(target)
    if model:
        params["model"] = model
    clamp_cfg = (target or {}).get("cfg")
    params["model"] = clamp_model(params.get("model"), cfg=clamp_cfg, route_id=route_id)
    if params.get("api_base"):
        params["model"] = _ensure_provider_prefix(params["model"])
    extra = _openrouter_extra(target or {})
    resolved_model = str(params.get("model") or model or "gpt-4o")

    retries = MAX_RETRIES if max_retries is None else max(1, int(max_retries))
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = completion(
                model=params["model"],
                messages=messages,
                **{k: v for k, v in params.items() if k != "model"},
                **extra,
                **kwargs,
            )
            text = _message_visible_text(response.choices[0].message)
            in_tok, out_tok = _usage_tokens(
                response,
                prompt=prompt,
                system=system,
                output_text=text,
            )
            _wallet_bill_llm(
                resolved_model,
                prompt=prompt,
                system=system,
                max_tokens=kwargs.get("max_tokens"),
                input_tokens=in_tok,
                output_tokens=out_tok,
                trace_label=trace_label,
            )
            return text
        except RateLimitError as exc:
            last_error = exc
            wait = RETRY_BACKOFF_SECONDS * attempt
            logger.warning(
                "LLM 速率限制，%.1f 秒後重試（%d/%d）", wait, attempt, retries
            )
            time.sleep(wait)
        except APIError as exc:
            last_error = exc
            logger.warning("LLM 呼叫失敗：%s，重試（%d/%d）", exc, attempt, retries)
            time.sleep(RETRY_BACKOFF_SECONDS)
    raise RuntimeError(f"LLM 呼叫於 {retries} 次重試後仍失敗") from last_error


def _build_call_hops(
    route_id: str | None,
    model: str | None,
    extra_models: list[str],
) -> list[tuple[str | None, str | None]]:
    """(route_id, model) 嘗試序列：主路由 → 角色備援模型 → API 備援鏈。"""
    hops: list[tuple[str | None, str | None]] = []
    seen: set[tuple[str, str]] = set()

    def _add(rid: str | None, mid: str | None) -> None:
        key = ((rid or "").strip(), (mid or "").strip())
        if key in seen:
            return
        seen.add(key)
        hops.append((rid, mid))

    try:
        from backend.core.api_router import list_failover_chain

        chain = list_failover_chain(route_id=route_id, model=model, extra_models=extra_models)
    except Exception:
        chain = []
    if not chain:
        _add(route_id, model)
        return hops

    _add(str(chain[0].get("id") or route_id or "") or route_id, model)
    for extra in extra_models:
        try:
            from backend.core.api_router import find_route_for_model

            owned = find_route_for_model(extra)
        except Exception:
            owned = None
        _add((owned or {}).get("id") or None, extra)
    for route in chain[1:]:
        _add(str(route.get("id") or "") or None, str(route.get("model") or model or "") or model)
    return hops or [(route_id, model)]


def call_llm(
    prompt: str,
    system: str | None = None,
    model: str | None = None,
    max_retries: int | None = None,
    *,
    route_id: str | None = None,
    max_context_tokens: int | None = None,
    role_failover_models: list[str] | None = None,
    trace_label: str = "",
    **kwargs,
) -> str:
    """呼叫 LLM 並回傳回應文字（統一軌跡鉤子點）。

    若處於任務上下文（llm_trace.trace_task_id 已綁定），自動記錄本調用的
    prompt/system/response/耗時 進任務軌跡，供角色 I/O 全監使用；
    trace_label 可附加語義標籤（如 execute/review/grill）。
    """
    from backend.core import llm_trace

    started = time.monotonic()
    try:
        result = _call_llm_core(
            prompt,
            system=system,
            model=model,
            max_retries=max_retries,
            route_id=route_id,
            max_context_tokens=max_context_tokens,
            role_failover_models=role_failover_models,
            trace_label=trace_label,
            **kwargs,
        )
    except Exception as exc:
        if llm_trace.current_context()["task_id"]:
            llm_trace.emit({
                "label": trace_label,
                "prompt": prompt,
                "system": system,
                "model": model,
                "response": "",
                "error": str(exc),
                "duration_ms": round((time.monotonic() - started) * 1000, 1),
            })
        raise
    if llm_trace.current_context()["task_id"]:
        llm_trace.emit({
            "label": trace_label,
            "prompt": prompt,
            "system": system,
            "model": model,
            "response": result,
            "duration_ms": round((time.monotonic() - started) * 1000, 1),
        })
    return result


def _call_llm_core(
    prompt: str,
    system: str | None = None,
    model: str | None = None,
    max_retries: int | None = None,
    *,
    route_id: str | None = None,
    max_context_tokens: int | None = None,
    role_failover_models: list[str] | None = None,
    trace_label: str = "",
    **kwargs,
) -> str:
    """呼叫 LLM 並回傳回應文字。

    內建指數退避重試，處理速率限制（RateLimitError）
    與暫時性 API 錯誤。

    max_retries 預設 3（與 MAX_RETRIES 相同），以保持反思閉環行為；
    Hub 路由器切模型前應傳 max_retries=1，避免 3×3 放大延遲。
    啟用 EVOL_LLM_POOL_FAILOVER 時，主模型逾時或限流會自動切換池內備援。
    多 API 路由時依 route_id / 模型歸屬選擇憑證；max_tokens / temperature
    可經 kwargs 傳入（角色 Token 限制）。主路由失敗且有備援路由時會跨 API 切換。
    """
    extras = role_failover_models or kwargs.pop("role_failover_models", None) or []
    extras = [str(item).strip() for item in extras if str(item).strip()]
    hops = _build_call_hops(route_id, model, extras)

    if len(hops) <= 1:
        hop_route, hop_model = hops[0] if hops else (route_id, model)
        return _call_llm_on_route(
            prompt,
            system=system,
            model=hop_model,
            max_retries=max_retries,
            route_id=hop_route,
            max_context_tokens=max_context_tokens,
            trace_label=trace_label,
            **kwargs,
        )

    last_error: Exception | None = None
    for hop, (hop_route_id, hop_model) in enumerate(hops):
        hop_retries = max_retries if hop == 0 else 1
        try:
            return _call_llm_on_route(
                prompt,
                system=system,
                model=hop_model,
                max_retries=hop_retries,
                route_id=hop_route_id,
                max_context_tokens=max_context_tokens,
                trace_label=trace_label,
                **kwargs,
            )
        except Exception as exc:
            last_error = exc
            if hop + 1 < len(hops):
                nxt = hops[hop + 1][0]
                logger.warning("API 路由 %s 失敗，切換備援 %s：%s", hop_route_id, nxt, exc)
                continue
            raise
    if last_error:
        raise last_error
    return _call_llm_on_route(
        prompt,
        system=system,
        model=model,
        max_retries=max_retries,
        route_id=route_id,
        max_context_tokens=max_context_tokens,
        trace_label=trace_label,
        **kwargs,
    )


def _call_llm_on_route(
    prompt: str,
    system: str | None = None,
    model: str | None = None,
    max_retries: int | None = None,
    *,
    route_id: str | None = None,
    max_context_tokens: int | None = None,
    trace_label: str = "",
    **kwargs,
) -> str:
    kwargs.pop("role_failover_models", None)
    tracked = ""
    try:
        target = _resolve_call_target(model, route_id)
        clamp_cfg = target.get("cfg")
        resolved_model = clamp_model(model or target.get("model"), cfg=clamp_cfg, route_id=route_id)
        params = _llm_params(target)
        tracked = str(route_id or target.get("route_id") or "")
    except Exception:
        params = _llm_params()
        clamp_cfg = None
        resolved_model = clamp_model(model or params.get("model"))
        target = None
        tracked = str(route_id or "")
    if params.get("api_base"):
        resolved_model = _ensure_provider_prefix(resolved_model)

    try:
        from backend.core.api_router import mark_route_end, mark_route_start

        mark_route_start(tracked)
    except Exception:
        mark_route_end = None  # type: ignore[assignment]

    try:
        prompt = _truncate_prompt(prompt, max_context_tokens)

        cache = get_llm_cache()
        cached = cache.get(prompt, system, resolved_model)
        if cached is not None:
            return cached

        call_kw = dict(kwargs)
        call_kw["route_id"] = route_id or (target or {}).get("route_id")
        call_kw["max_context_tokens"] = max_context_tokens

        if pool_failover_enabled():
            chain = failover_models(resolved_model, cfg=clamp_cfg)
            if len(chain) > 1:
                text, used_model, hops = invoke_with_pool_failover(
                    _completion_once,
                    prompt=prompt,
                    system=system,
                    models=chain,
                    max_retries=max_retries,
                    trace_label=trace_label,
                    **call_kw,
                )
                if hops > 0:
                    logger.info(
                        "模型池 Failover：%s → %s（跳過 %d 個）",
                        resolved_model,
                        used_model,
                        hops,
                    )
                cache.put(prompt, system, used_model, text)
                return text

        result = _completion_once(
            prompt=prompt,
            system=system,
            model=resolved_model,
            max_retries=max_retries,
            trace_label=trace_label,
            **call_kw,
        )
        cache.put(prompt, system, resolved_model, result)
        return result
    finally:
        if mark_route_end is not None:
            try:
                mark_route_end(tracked)
            except Exception:
                pass


def llm_kwargs_for_role(runtime: dict | None) -> dict:
    """把角色設定轉成 call_llm 參數（供應商、Token、溫度）。"""
    if not runtime:
        return {}
    out: dict = {}
    provider = str(runtime.get("preferred_provider") or "").strip()
    if provider:
        try:
            from backend.core.api_router import resolve_route_ref

            route = resolve_route_ref(provider)
            out["route_id"] = (route or {}).get("id") or provider
        except Exception:
            out["route_id"] = provider
    failover = [
        str(item).strip()
        for item in (runtime.get("failover_models") or [])
        if str(item).strip()
    ]
    if failover:
        out["role_failover_models"] = failover
    try:
        tokens = int(runtime.get("max_output_tokens") or 0)
    except (TypeError, ValueError):
        tokens = 0
    if tokens > 0:
        out["max_tokens"] = tokens
    if runtime.get("temperature") is not None:
        try:
            out["temperature"] = float(runtime["temperature"])
        except (TypeError, ValueError):
            pass
    ctx = runtime.get("context_window") or runtime.get("max_context_tokens")
    try:
        ctx_n = int(ctx or 0)
    except (TypeError, ValueError):
        ctx_n = 0
    if ctx_n > 0:
        out["max_context_tokens"] = ctx_n
    retries = runtime.get("max_retries")
    if retries is not None:
        try:
            out["max_retries"] = max(1, int(retries))
        except (TypeError, ValueError):
            pass
    return out


def call_llm_stream(
    prompt: str,
    system: str | None = None,
    model: str | None = None,
    max_retries: int | None = None,
    *,
    route_id: str | None = None,
    max_context_tokens: int | None = None,
    trace_label: str = "",
    **kwargs,
):
    """呼叫 LLM 並串流回傳回應片段（生成器）。

    與 call_llm 相同的重試邏輯，但逐塊 yield 文字。
    """
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": _truncate_prompt(prompt, max_context_tokens)})

    try:
        target = _resolve_call_target(model, route_id)
    except Exception:
        target = None
    params = _llm_params(target)
    if model:
        params["model"] = model
    clamp_cfg = (target or {}).get("cfg")
    params["model"] = clamp_model(params.get("model"), cfg=clamp_cfg, route_id=route_id)
    if params.get("api_base"):
        params["model"] = _ensure_provider_prefix(params["model"])
    extra = _openrouter_extra(target or {})
    resolved_model = str(params.get("model") or model or "gpt-4o")

    from backend.billing.errors import FeatureNotEntitledError, InsufficientCreditsError
    from backend.billing.metering import meter_llm, precheck_llm

    retries = MAX_RETRIES if max_retries is None else max(1, int(max_retries))
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            try:
                precheck_llm(
                    resolved_model,
                    max(1, len(prompt) // 4 + len(system or "") // 4),
                    int(kwargs.get("max_tokens") or 2048),
                )
            except (InsufficientCreditsError, FeatureNotEntitledError) as exc:
                raise RuntimeError(exc.message) from exc
            response = completion(
                model=params["model"],
                messages=messages,
                stream=True,
                **{k: v for k, v in params.items() if k != "model"},
                **extra,
                **kwargs,
            )
            in_think = False
            collected: list[str] = []
            for chunk in response:
                delta = chunk.choices[0].delta if chunk.choices else None
                reasoning = _delta_reasoning(delta)
                content = getattr(delta, "content", None) if delta else None
                if reasoning:
                    if not in_think:
                        yield "<think>"
                        in_think = True
                    collected.append(reasoning)
                    yield reasoning
                if content:
                    if in_think:
                        yield "</think>"
                        in_think = False
                    collected.append(content)
                    yield content
            if in_think:
                yield "</think>"
            output_text = "".join(collected)
            in_tok = max(1, len(prompt) // 4 + len(system or "") // 4)
            out_tok = max(1, len(output_text) // 4)
            try:
                meter_llm(
                    resolved_model,
                    in_tok,
                    out_tok,
                    reference=trace_label or "stream",
                    meta={"trace_label": trace_label or "stream"},
                )
            except (InsufficientCreditsError, FeatureNotEntitledError) as exc:
                raise RuntimeError(exc.message) from exc
            return
        except RateLimitError as exc:
            last_error = exc
            wait = RETRY_BACKOFF_SECONDS * attempt
            logger.warning(
                "LLM 速率限制，%.1f 秒後重試（%d/%d）", wait, attempt, retries
            )
            time.sleep(wait)
        except APIError as exc:
            last_error = exc
            logger.warning("LLM 呼叫失敗：%s，重試（%d/%d）", exc, attempt, retries)
            time.sleep(RETRY_BACKOFF_SECONDS)
    raise RuntimeError(f"LLM 呼叫於 {retries} 次重試後仍失敗") from last_error


def parse_json_response(text: str) -> dict:
    """穩健地解析 LLM 回傳的 JSON。

    依序嘗試：直接解析 → 去除 markdown 程式碼圍欄 →
    擷取最外層 {...} 區塊。
    """
    text = split_thinking(text)[1] or (text or "").strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise