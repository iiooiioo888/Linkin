"""路由表展平工具（版本無關）。

FastAPI 0.162 起 ``app.include_router()`` 會把子 router 記成 ``_IncludedRouter``
（繼承 ``BaseRoute``，不是 ``Route``），路由要經 ``effective_candidates()`` 才展開；
且該展開可能再回傳巢狀 ``_IncludedRouter``。因此快照與比對都必須用本模組，
不能用 ``isinstance(route, Route)`` 這種寫法——那在原版 FastAPI 可用，
在這版會**靜默漏掉全部子 router 路由**（實測只看到 132 條，實際 300+）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RouteEntry:
    """一條路由的比對鍵：path + methods + name。"""

    path: str
    methods: tuple[str, ...]
    name: str

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "methods": list(self.methods), "name": self.name}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> RouteEntry:
        return cls(
            path=str(raw["path"]),
            methods=tuple(sorted(raw.get("methods") or [])),
            name=str(raw.get("name") or ""),
        )


def _methods_of(route: Any) -> tuple[str, ...]:
    raw = getattr(route, "methods", None)
    if not raw:
        return ("WS",)
    return tuple(sorted(str(m) for m in raw))


def flatten_routes(routes: Any) -> list[RouteEntry]:
    """把 ``app.routes`` 遞迴展平成 ``RouteEntry`` 清單（保留宣告順序）。"""
    out: list[RouteEntry] = []

    def walk(items: Any) -> None:
        for route in items:
            path = getattr(route, "path", None)
            if path is not None and hasattr(route, "endpoint"):
                out.append(
                    RouteEntry(
                        path=str(path),
                        methods=_methods_of(route),
                        name=str(getattr(route, "name", "") or ""),
                    )
                )
                continue
            candidates = getattr(route, "effective_candidates", None)
            if callable(candidates):
                for candidate in candidates():
                    candidate_path = getattr(candidate, "path", None)
                    if candidate_path is None:
                        # 巢狀 _IncludedRouter：再遞迴
                        walk([candidate])
                        continue
                    out.append(
                        RouteEntry(
                            path=str(candidate_path),
                            methods=_methods_of(candidate),
                            name=str(getattr(candidate, "name", "") or ""),
                        )
                    )

    walk(routes)
    return out
