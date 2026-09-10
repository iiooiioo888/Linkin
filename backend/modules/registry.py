"""世界／整合模組註冊表。

控制台（EvoLoop）與可插拔模組分離：新模組實作 ``ModuleSpec`` 並
``register_module``，即可出現在 ``GET /modules`` 與前端活動欄。
既有業務仍走各模組自己的 API（Minecraft 為 ``/linkin/*``），本層只提供
目錄、頁面、能力與健康檢查的統一契約。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

HealthFn = Callable[[], dict[str, Any]]


@dataclass(frozen=True)
class ModuleCapability:
    """模組對外能力（給目錄與前端對照，不取代實作路由）。"""

    id: str
    title: str
    description: str
    api_prefix: str
    routes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "api_prefix": self.api_prefix,
            "routes": list(self.routes),
        }


@dataclass(frozen=True)
class ModuleNavItem:
    key: str
    icon: str
    label: str
    hint: str = ""
    capability: str = ""
    roster: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = {"key": self.key, "icon": self.icon, "label": self.label, "hint": self.hint}
        if self.capability:
            payload["capability"] = self.capability
        if self.roster:
            payload["roster"] = self.roster
        return payload


@dataclass(frozen=True)
class ModuleNavGroup:
    id: str
    label: str
    items: tuple[ModuleNavItem, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "items": [item.to_dict() for item in self.items],
        }


@dataclass(frozen=True)
class ModuleSpec:
    id: str
    title: str
    description: str
    version: str = "1.0.0"
    kind: str = "world"
    icon: str = "generic"
    default_page: str = ""
    enabled: bool = True
    api_prefix: str = ""
    capabilities: tuple[ModuleCapability, ...] = ()
    nav_groups: tuple[ModuleNavGroup, ...] = ()
    page_aliases: tuple[tuple[str, str], ...] = ()
    health: HealthFn | None = field(default=None, compare=False, hash=False)

    def capability_map(self) -> dict[str, ModuleCapability]:
        return {cap.id: cap for cap in self.capabilities}

    def pages(self) -> list[dict[str, Any]]:
        """扁平頁面目錄：導航鍵 + 對應能力路由，給前端宿主與後續模組共用。"""
        caps = self.capability_map()
        out: list[dict[str, Any]] = []
        for group in self.nav_groups:
            for item in group.items:
                cap = caps.get(item.capability)
                out.append(
                    {
                        "key": item.key,
                        "group": group.id,
                        "group_label": group.label,
                        "icon": item.icon,
                        "label": item.label,
                        "hint": item.hint,
                        "capability": item.capability or None,
                        "api_prefix": cap.api_prefix if cap else self.api_prefix,
                        "routes": list(cap.routes) if cap else [],
                        "roster": item.roster or None,
                    }
                )
        return out

    def page(self, key: str) -> dict[str, Any] | None:
        needle = (key or "").strip()
        if not needle:
            return None
        for item in self.pages():
            if item["key"] == needle:
                return item
        return None

    def allowed_routes(self) -> tuple[str, ...]:
        """能力路由允許清單（閘道轉發用）。"""
        seen: list[str] = []
        for cap in self.capabilities:
            for route in cap.routes:
                if route not in seen:
                    seen.append(route)
        return tuple(seen)

    def gateway_prefix(self) -> str:
        return f"/modules/{self.id}/api"

    def to_dict(self, *, include_health: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "version": self.version,
            "kind": self.kind,
            "icon": self.icon,
            "default_page": self.default_page,
            "enabled": self.enabled,
            "api_prefix": self.api_prefix,
            "gateway_prefix": self.gateway_prefix(),
            "capabilities": [cap.to_dict() for cap in self.capabilities],
            "nav_groups": [group.to_dict() for group in self.nav_groups],
            "pages": self.pages(),
            "page_aliases": {src: dest for src, dest in self.page_aliases},
        }
        if include_health:
            payload["health"] = self.health_snapshot()
        return payload

    def health_snapshot(self) -> dict[str, Any]:
        if self.health is None:
            return {"ok": True, "id": self.id}
        try:
            data = dict(self.health() or {})
        except Exception as exc:  # noqa: BLE001 — 目錄不得因單一模組健康檢查失敗而 500
            return {"ok": False, "id": self.id, "error": str(exc)}
        data.setdefault("id", self.id)
        data.setdefault("ok", True)
        return data


_REGISTRY: dict[str, ModuleSpec] = {}


def reset_registry() -> None:
    """測試隔離：清空已註冊模組。"""
    _REGISTRY.clear()


def register_module(spec: ModuleSpec) -> ModuleSpec:
    if not spec.id or spec.id.strip() != spec.id:
        raise ValueError("模組 id 不可為空")
    if spec.id in {"chat", "console", "lab", "monitor", "modules", "api"}:
        raise ValueError(f"模組 id 與核心活動衝突：{spec.id}")
    _REGISTRY[spec.id] = spec
    return spec


def get_module(module_id: str) -> ModuleSpec | None:
    return _REGISTRY.get(module_id)


def list_modules(*, include_disabled: bool = False) -> list[ModuleSpec]:
    specs = list(_REGISTRY.values())
    if not include_disabled:
        specs = [item for item in specs if item.enabled]
    return specs


def module_page_keys(module_id: str) -> set[str]:
    spec = get_module(module_id)
    if spec is None:
        return set()
    return {item.key for group in spec.nav_groups for item in group.items}
