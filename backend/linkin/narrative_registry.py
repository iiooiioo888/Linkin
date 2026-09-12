"""敘事工作區全域註冊表（程序生命週期單例）。"""

from __future__ import annotations

from backend.linkin.narrative_workspace import WorkspaceRegistry

_registry: WorkspaceRegistry | None = None


def get_narrative_registry() -> WorkspaceRegistry:
    global _registry
    if _registry is None:
        _registry = WorkspaceRegistry()
    return _registry


def reset_narrative_registry() -> None:
    """測試用：清空單例。"""
    global _registry
    _registry = None


__all__ = ["get_narrative_registry", "reset_narrative_registry"]
