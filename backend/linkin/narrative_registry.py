"""敘事工作區全域註冊表（程序生命週期單例）。"""

from __future__ import annotations

from backend.linkin.narrative_workspace import WorkspaceRegistry

_registry: WorkspaceRegistry | None = None


def get_narrative_registry() -> WorkspaceRegistry:
    global _registry
    if _registry is None:
        _registry = WorkspaceRegistry()
    return _registry


def restart_narrative_registry() -> None:
    """模擬程序重啟：丟棄單例但保留磁碟草稿。"""
    global _registry
    _registry = None


def reset_narrative_registry() -> None:
    """測試用：清空單例與磁碟草稿。"""
    global _registry
    if _registry is not None:
        _registry.clear_persistence()
    else:
        from backend.linkin.narrative_workspace import _default_persist_path

        path = _default_persist_path()
        if path.exists():
            path.unlink()
    _registry = None


__all__ = ["get_narrative_registry", "reset_narrative_registry", "restart_narrative_registry"]
