"""LLM 呼叫層（自 backend.core.llm 抽出）。

參數解析、供應商前綴、提示截斷、OpenRouter extra、思考過程拆分與訊息文字 helper。
"""

from __future__ import annotations

import re

from ._compat import _ensure_provider_prefix as _pkg_ensure_provider_prefix
from ._compat import get_runtime_config

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
            params["model"] = _pkg_ensure_provider_prefix(params["model"])
        return params
    cfg = get_runtime_config()
    params = {"model": cfg.get("model") or "gpt-4o"}
    if cfg.get("api_key"):
        params["api_key"] = cfg["api_key"]
    if cfg.get("api_base"):
        params["api_base"] = cfg["api_base"]
        params["model"] = _pkg_ensure_provider_prefix(params["model"])
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
