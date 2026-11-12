"""測試 patch 相容層：呼叫當下才解析回 backend.core.llm 套件層屬性。


重構前 llm 是單一模組，測試以 monkeypatch.setattr(backend.core.llm.<name>, fake)
替換模組屬性；呼叫端在同一模組內用 global 查找，因此 patch 立即生效。
拆成套件後，子模組若直接 from .x import <name> 會綁定原始函式物件，
patch 套件層屬性不會影響已綁定參照。因此所有內部呼叫一律經過本模組，
於呼叫當下解析回套件層屬性（與 hub/service 的 call_llm 相同原理）。
"""

from __future__ import annotations

from typing import Any


def _target() -> Any:
    """回傳 backend.core.llm 套件模組（呼叫當下才匯入，避免循環）。"""
    from backend.core import llm as _package

    return _package


def completion(*args: Any, **kwargs: Any) -> Any:
    """延遲解析 completion：永遠走套件層屬性（可被測試 patch）。"""
    return _target().completion(*args, **kwargs)


def clamp_model(*args: Any, **kwargs: Any) -> Any:
    """延遲解析 clamp_model：永遠走套件層屬性（可被測試 patch）。"""
    return _target().clamp_model(*args, **kwargs)


def failover_models(*args: Any, **kwargs: Any) -> Any:
    """延遲解析 failover_models：永遠走套件層屬性（可被測試 patch）。"""
    return _target().failover_models(*args, **kwargs)


def invoke_with_pool_failover(*args: Any, **kwargs: Any) -> Any:
    """延遲解析 invoke_with_pool_failover：永遠走套件層屬性（可被測試 patch）。"""
    return _target().invoke_with_pool_failover(*args, **kwargs)


def pool_failover_enabled(*args: Any, **kwargs: Any) -> Any:
    """延遲解析 pool_failover_enabled：永遠走套件層屬性（可被測試 patch）。"""
    return _target().pool_failover_enabled(*args, **kwargs)


def get_llm_cache(*args: Any, **kwargs: Any) -> Any:
    """延遲解析 get_llm_cache：永遠走套件層屬性（可被測試 patch）。"""
    return _target().get_llm_cache(*args, **kwargs)


def get_runtime_config(*args: Any, **kwargs: Any) -> Any:
    """延遲解析 get_runtime_config：永遠走套件層屬性（可被測試 patch）。"""
    return _target().get_runtime_config(*args, **kwargs)


def _llm_params(*args: Any, **kwargs: Any) -> Any:
    """延遲解析 _llm_params：永遠走套件層屬性（可被測試 patch）。"""
    return _target()._llm_params(*args, **kwargs)


def _resolve_call_target(*args: Any, **kwargs: Any) -> Any:
    """延遲解析 _resolve_call_target：永遠走套件層屬性（可被測試 patch）。"""
    return _target()._resolve_call_target(*args, **kwargs)


def _truncate_prompt(*args: Any, **kwargs: Any) -> Any:
    """延遲解析 _truncate_prompt：永遠走套件層屬性（可被測試 patch）。"""
    return _target()._truncate_prompt(*args, **kwargs)


def _openrouter_extra(*args: Any, **kwargs: Any) -> Any:
    """延遲解析 _openrouter_extra：永遠走套件層屬性（可被測試 patch）。"""
    return _target()._openrouter_extra(*args, **kwargs)


def _ensure_provider_prefix(*args: Any, **kwargs: Any) -> Any:
    """延遲解析 _ensure_provider_prefix：永遠走套件層屬性（可被測試 patch）。"""
    return _target()._ensure_provider_prefix(*args, **kwargs)


def split_thinking(*args: Any, **kwargs: Any) -> Any:
    """延遲解析 split_thinking：永遠走套件層屬性（可被測試 patch）。"""
    return _target().split_thinking(*args, **kwargs)


def _delta_reasoning(*args: Any, **kwargs: Any) -> Any:
    """延遲解析 _delta_reasoning：永遠走套件層屬性（可被測試 patch）。"""
    return _target()._delta_reasoning(*args, **kwargs)


def _message_visible_text(*args: Any, **kwargs: Any) -> Any:
    """延遲解析 _message_visible_text：永遠走套件層屬性（可被測試 patch）。"""
    return _target()._message_visible_text(*args, **kwargs)


def _usage_tokens(*args: Any, **kwargs: Any) -> Any:
    """延遲解析 _usage_tokens：永遠走套件層屬性（可被測試 patch）。"""
    return _target()._usage_tokens(*args, **kwargs)


def _wallet_bill_llm(*args: Any, **kwargs: Any) -> Any:
    """延遲解析 _wallet_bill_llm：永遠走套件層屬性（可被測試 patch）。"""
    return _target()._wallet_bill_llm(*args, **kwargs)


def _completion_once(*args: Any, **kwargs: Any) -> Any:
    """延遲解析 _completion_once：永遠走套件層屬性（可被測試 patch）。"""
    return _target()._completion_once(*args, **kwargs)


def _build_call_hops(*args: Any, **kwargs: Any) -> Any:
    """延遲解析 _build_call_hops：永遠走套件層屬性（可被測試 patch）。"""
    return _target()._build_call_hops(*args, **kwargs)


def _call_llm_on_route(*args: Any, **kwargs: Any) -> Any:
    """延遲解析 _call_llm_on_route：永遠走套件層屬性（可被測試 patch）。"""
    return _target()._call_llm_on_route(*args, **kwargs)
