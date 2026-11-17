"""組件契約（ComponentSpec）。

對齊 DSH（DeepSeek Harness）／Cordis 的 **host bundle + client section** 概念：

- host bundle：一組後端路由 + 生命週期掛鉤 + 護欄要求（:class:`ComponentSpec`）
- client section：導覽項與前端掛載點（:class:`ComponentSurface`）

與既有 ``ModuleSpec`` 的關係：``ModuleSpec`` 是**目錄描述**（對外 JSON 契約，
``GET /modules`` 的回應形狀），``ComponentSpec`` 是**可安裝單位**。
``ComponentSpec.to_module_spec()`` 把描述投影回 ``ModuleSpec``，
只有 ``exposed_in_catalog=True`` 的組件才會進 ``GET /modules``——
因此收編既有功能不會改變該端點的任何輸出。

契約測試見 ``backend/tests/test_component_contract.py``。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi import APIRouter

from backend.modules.registry import (
    HealthFn,
    ModuleCapability,
    ModuleNavGroup,
    ModuleNavItem,
    ModuleSpec,
)

#: 組件類別。前三個對應 ``docs/structure.md`` 的三分類；``world`` 保留給靈境類世界模組。
ComponentKind = Literal["core", "price", "integration", "world"]

#: 插件來源標籤（沿用 TODO §6.2 的 ``deepseek-club`` / ``dsh-plugin``）。
ComponentSource = Literal["builtin", "deepseek-club", "dsh-plugin"]

#: 生命週期狀態。刻意與 ``backend.modules.plugin_manager.PluginStatus`` 同名同值，
#: 不對外匯出第二套詞彙。
ComponentStatus = Literal["installed", "enabled", "disabled", "degraded"]

#: 前端掛載點種類。
MountKind = Literal["page", "panel", "chat_bottom", "task_detail", "settings", "modal"]

#: 護欄種類。每一種都必須對應到**既有**的強制點，不得自造旁路。
GuardKind = Literal["opc_write", "llm", "billing", "tenant", "auth", "api_key", "filesystem"]

#: 整合類的六個功能分組，與 ``frontend/src/lib/labTabs.ts`` 的
#: ``LAB_INTEGRATE_SECTIONS`` id 完全同名。
INTEGRATION_SECTIONS: tuple[str, ...] = (
    "recall",
    "crawl",
    "wire",
    "agent",
    "design",
    "skills",
)

#: ``GET /modules`` 端點不可投影的 id（既有的核心活動命名空間）。
#: 這個清單屬於**投影層**；``ComponentSpec.id`` 本身可用這些名字。
CATALOG_RESERVED_IDS: frozenset[str] = frozenset(
    {"chat", "console", "lab", "monitor", "modules", "api"}
)


@dataclass(frozen=True)
class GuardRequirement:
    """宣告式護欄要求：說明「這個組件必須經過哪個既有強制點」。

    ``enforced_by`` 必須是**已存在**的模組路徑（例：``opc_service.guard``）。
    契約測試會用 AST 檢查對應實作真的 import 了它，避免宣告與實作脫節。
    """

    kind: GuardKind
    detail: str = ""
    enforced_by: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "detail": self.detail, "enforced_by": self.enforced_by}


@dataclass(frozen=True)
class ComponentCapability:
    """組件對外能力。

    比 ``ModuleCapability`` 多了 ``methods`` 與 ``write``：
    閘道可據此區分讀寫，契約測試可據 ``write=True`` 要求對應的寫入護欄。
    """

    id: str
    title: str
    description: str = ""
    api_prefix: str = ""
    routes: tuple[str, ...] = ()
    methods: tuple[str, ...] = ()
    write: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "api_prefix": self.api_prefix,
            "routes": list(self.routes),
            "methods": list(self.methods),
            "write": self.write,
        }

    def to_module_capability(self) -> ModuleCapability:
        return ModuleCapability(
            id=self.id,
            title=self.title,
            description=self.description,
            api_prefix=self.api_prefix,
            routes=self.routes,
        )


@dataclass(frozen=True)
class ComponentNavGroup:
    """導覽分組（延續 ``ModuleNavGroup`` 的形狀，另帶區域與可選的來源標籤）。"""

    id: str
    label: str
    items: tuple[ModuleNavItem, ...] = ()
    area: Literal["console", "lab", "world"] = "world"
    plane: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "label": self.label,
            "items": [item.to_dict() for item in self.items],
            "area": self.area,
        }
        if self.plane:
            payload["plane"] = self.plane
        return payload

    def to_module_nav_group(self) -> ModuleNavGroup:
        return ModuleNavGroup(id=self.id, label=self.label, items=self.items)


@dataclass(frozen=True)
class ComponentSurface:
    """前端面：一個組件可以掛在多個位置（整頁／面板／對話底部／任務詳情…）。

    ``lazy_entry`` 只是給前端的 import 提示（例如 ``modules/media-vault/register``），
    實際 loader 仍由前端註冊表持有——後端不引用任何 JS。
    """

    mount: MountKind
    key: str
    label: str
    icon: str = "generic"
    hint: str = ""
    nav_group: str = ""
    lazy_entry: str = ""
    capability: str = ""
    aliases: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "mount": self.mount,
            "key": self.key,
            "label": self.label,
            "icon": self.icon,
            "hint": self.hint,
        }
        if self.nav_group:
            payload["nav_group"] = self.nav_group
        if self.lazy_entry:
            payload["lazy_entry"] = self.lazy_entry
        if self.capability:
            payload["capability"] = self.capability
        if self.aliases:
            payload["aliases"] = list(self.aliases)
        return payload


HookFn = Callable[[], None]
AsyncHookFn = Callable[[], Awaitable[None]]


@dataclass(frozen=True)
class ComponentSpec:
    """一個可安裝功能的完整宣告：host bundle + client section。"""

    # ── 身分 ──
    id: str
    title: str
    description: str = ""
    version: str = "1.0.0"
    kind: ComponentKind = "integration"
    source: ComponentSource = "builtin"
    pin: str = ""
    icon: str = "generic"

    # ── 後端路由（host bundle）──
    router: APIRouter | None = field(default=None, compare=False, hash=False)
    api_prefix: str = ""
    capabilities: tuple[ComponentCapability, ...] = ()
    openapi_tags: tuple[str, ...] = ()
    include_in_schema: bool = True
    gate_open_paths: tuple[str, ...] = ()

    # ── 前端面（client section）──
    surfaces: tuple[ComponentSurface, ...] = ()
    nav_groups: tuple[ComponentNavGroup, ...] = ()
    page_aliases: tuple[tuple[str, str], ...] = ()
    default_page: str = ""

    # ── 健康 ──
    health: HealthFn | None = field(default=None, compare=False, hash=False)
    health_timeout_s: float = 2.0

    # ── 生命週期 ──
    enabled: bool = True
    exposed_in_catalog: bool = False
    requires: tuple[str, ...] = ()
    optional_requires: tuple[str, ...] = ()

    # ── 權限與護欄 ──
    guards: tuple[GuardRequirement, ...] = ()
    max_mount_layer: str = "L2"
    billing_feature: str = ""
    tenant_required: bool = False

    # ── 掛鉤 ──
    on_install: HookFn | None = field(default=None, compare=False, hash=False)
    on_enable: HookFn | None = field(default=None, compare=False, hash=False)
    on_disable: HookFn | None = field(default=None, compare=False, hash=False)
    on_startup: AsyncHookFn | None = field(default=None, compare=False, hash=False)
    on_shutdown: AsyncHookFn | None = field(default=None, compare=False, hash=False)

    # ── 查詢輔助 ──

    def capability_map(self) -> dict[str, ComponentCapability]:
        return {cap.id: cap for cap in self.capabilities}

    def page_keys(self) -> set[str]:
        return {item.key for group in self.nav_groups for item in group.items}

    def surface_keys(self) -> set[str]:
        return {surface.key for surface in self.surfaces}

    def allowed_routes(self) -> tuple[str, ...]:
        seen: list[str] = []
        for cap in self.capabilities:
            for route in cap.routes:
                if route not in seen:
                    seen.append(route)
        return tuple(seen)

    def write_capabilities(self) -> tuple[ComponentCapability, ...]:
        return tuple(cap for cap in self.capabilities if cap.write)

    def guard_kinds(self) -> set[str]:
        return {guard.kind for guard in self.guards}

    def gateway_prefix(self) -> str:
        return f"/modules/{self.id}/api"

    def is_catalog_exposed(self) -> bool:
        """能否安全投影進 ``GET /modules``（id 不與核心活動命名空間衝突）。"""
        return self.exposed_in_catalog and self.id not in CATALOG_RESERVED_IDS

    # ── 投影 ──

    def to_module_spec(self) -> ModuleSpec:
        """投影成 ``GET /modules`` 用的 ``ModuleSpec``（形狀與既有完全一致）。"""
        if self.id in CATALOG_RESERVED_IDS:
            raise ValueError(f"組件 id 不可投影進模組目錄（與核心活動衝突）：{self.id}")
        return ModuleSpec(
            id=self.id,
            title=self.title,
            description=self.description,
            version=self.version,
            kind=self.kind,
            icon=self.icon,
            default_page=self.default_page,
            enabled=self.enabled,
            api_prefix=self.api_prefix,
            capabilities=tuple(cap.to_module_capability() for cap in self.capabilities),
            nav_groups=tuple(group.to_module_nav_group() for group in self.nav_groups),
            page_aliases=self.page_aliases,
            health=self.health,
        )

    @classmethod
    def from_module_spec(
        cls,
        spec: ModuleSpec,
        *,
        surfaces: tuple[ComponentSurface, ...] = (),
        router: APIRouter | None = None,
        guards: tuple[GuardRequirement, ...] = (),
        write_capability_ids: tuple[str, ...] = (),
        **overrides: Any,
    ) -> ComponentSpec:
        """從既有 ``ModuleSpec`` 建成組件宣告。

        用於「已經有 ``build_*_spec()`` 的模組」：直接沿用原 builder，
        投影回 ``ModuleSpec`` 時欄位逐位相同（``test_projection_roundtrip`` 驗證），
        所以收編過程不會改變 ``GET /modules`` 的任何輸出。

        ``write_capability_ids`` 標記哪些能力含寫入路由（模組目錄不表達這件事，
        只有組件契約表達；用來讓護欄要求可被靜態驗證）。
        """
        write_ids = set(write_capability_ids)
        capabilities = tuple(
            ComponentCapability(
                id=cap.id,
                title=cap.title,
                description=cap.description,
                api_prefix=cap.api_prefix,
                routes=cap.routes,
                write=cap.id in write_ids,
            )
            for cap in spec.capabilities
        )
        area = overrides.pop("area", "world")
        nav_groups = tuple(
            ComponentNavGroup(id=group.id, label=group.label, items=group.items, area=area)
            for group in spec.nav_groups
        )
        payload: dict[str, Any] = {
            "id": spec.id,
            "title": spec.title,
            "description": spec.description,
            "version": spec.version,
            "kind": spec.kind,
            "icon": spec.icon,
            "default_page": spec.default_page,
            "enabled": spec.enabled,
            "exposed_in_catalog": True,
            "api_prefix": spec.api_prefix,
            "capabilities": capabilities,
            "nav_groups": nav_groups,
            "page_aliases": spec.page_aliases,
            "health": spec.health,
            "surfaces": surfaces,
            "router": router,
            "guards": guards,
        }
        payload.update(overrides)
        return cls(**payload)  # type: ignore[arg-type]

    def to_dict(self, *, status: ComponentStatus | None = None) -> dict[str, Any]:
        """序列化為 manifest 條目（前端與外部客戶端共用同一份 JSON）。"""
        payload: dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "version": self.version,
            "kind": self.kind,
            "source": self.source,
            "status": status or ("enabled" if self.enabled else "installed"),
            "enabled": self.enabled,
            "exposed_in_catalog": self.is_catalog_exposed(),
            "api_prefix": self.api_prefix,
            "gateway_prefix": self.gateway_prefix(),
            "capabilities": [cap.to_dict() for cap in self.capabilities],
            "surfaces": [surface.to_dict() for surface in self.surfaces],
            "nav_groups": [group.to_dict() for group in self.nav_groups],
            "page_aliases": {src: dest for src, dest in self.page_aliases},
            "default_page": self.default_page,
            "requires": list(self.requires),
            "optional_requires": list(self.optional_requires),
            "guards": [guard.to_dict() for guard in self.guards],
            "max_mount_layer": self.max_mount_layer,
        }
        if self.pin:
            payload["pin"] = self.pin
        if self.billing_feature:
            payload["billing_feature"] = self.billing_feature
        if self.tenant_required:
            payload["tenant_required"] = True
        if self.gate_open_paths:
            payload["gate_open_paths"] = list(self.gate_open_paths)
        if self.openapi_tags:
            payload["openapi_tags"] = list(self.openapi_tags)
        return payload

    def health_snapshot(self) -> dict[str, Any]:
        """健康檢查：``degraded``／``disabled`` 時仍回結構化結果，不拋例外。"""
        if not self.enabled:
            return {"ok": False, "id": self.id, "reason": "disabled"}
        if self.health is None:
            return {"ok": True, "id": self.id}
        try:
            data = dict(self.health() or {})
        except Exception as exc:
            return {"ok": False, "id": self.id, "error": str(exc)}
        data.setdefault("id", self.id)
        data.setdefault("ok", True)
        return data
