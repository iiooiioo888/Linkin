"""測試 patch 相容層：於呼叫時解析套件層 _make_session／probe_server（monkeypatch 表面）。

套件化後實作在 sessions.py／registry.py，但既有測試以
monkeypatch.setattr(mcp_clients, "_make_session", ...) 等方式替換套件層屬性；
此包裝函式每次呼叫都重新讀取套件屬性，維持原本 patch 語意。
"""

from __future__ import annotations

from typing import Any


def _make_session(server: Any) -> Any:
    """轉呼叫套件層 _make_session（可能已被 monkeypatch 替換）。"""
    from backend.company import mcp_clients as _pkg

    return _pkg._make_session(server)


def probe_server(server: Any) -> Any:
    """轉呼叫套件層 probe_server（可能已被 monkeypatch 替換）。"""
    from backend.company import mcp_clients as _pkg

    return _pkg.probe_server(server)
