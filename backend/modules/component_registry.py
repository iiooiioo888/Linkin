"""組件註冊表與安裝器。

單一入口 :func:`install_components` 取代 ``backend/main.py`` 散落的
``register_*(app)`` 呼叫。安裝流程固定：

1. 解析 ``enabled``（``LINKIN_COMPONENT_DISABLED`` 環境變數可再關閉）
2. 依 ``requires`` 拓撲排序（缺依賴 → 該組件 ``degraded``，不擋其他組件）
3. 依序 ``app.include_router(component.router)``（順序即宣告順序）
4. 驗證 ``gate_open_paths`` 已被 AuthGate 放行（只驗證，不改它）
5. 收集 ``on_startup`` / ``on_shutdown`` 給 lifespan 執行
6. 投影：``exposed_in_catalog=True`` 的組件轉成 ``ModuleSpec`` 進 ``GET /modules``

契約測試見 ``backend/tests/test_component_contract.py``。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

from backend.modules.component import ComponentSpec, ComponentStatus
from backend.modules.registry import register_module

logger = logging.getLogger(__name__)

_REGISTRY: dict[str, ComponentSpec] = {}
_STATUS: dict[str, ComponentStatus] = {}
_REASONS: dict[str, str] = {}

#: 順序敏感：``GET /modules`` 的輸出順序由投影順序決定，
#: 既有測試 ``test_modules.py`` 斷言 ``["media-vault", "local-video-studio"]``。
#: 新增內建組件時**追加在尾端**，不要插隊或按字母排序。
BUILTIN_COMPONENT_MODULES: tuple[str, ...] = (
    "backend.modules.media_vault_component",
    "backend.modules.local_video_studio_component",
)

#: 環境變數：逗號分隔的組件 id，用於臨時停用（不影響原始宣告）。
DISABLED_ENV = "LINKIN_COMPONENT_DISABLED"


class ComponentDependencyError(ValueError):
    """未知依賴或依賴成環。"""


def reset_components() -> None:
    """測試隔離：清空組件註冊表與狀態。"""
    _REGISTRY.clear()
    _STATUS.clear()
    _REASONS.clear()


def get_builtin_components() -> list[ComponentSpec]:
    """回傳全部內建組件宣告（依 ``BUILTIN_COMPONENT_MODULES`` 順序）。

    純函式：不註冊、不落盤，供 manifest 匯出與契約測試重複呼叫。
    """
    import importlib

    specs: list[ComponentSpec] = []
    for module_path in BUILTIN_COMPONENT_MODULES:
        module = importlib.import_module(module_path)
        specs.append(module.build_component())
    return specs


def register_component(spec: ComponentSpec) -> ComponentSpec:
    """註冊（不安裝）單一組件。重複 id 直接覆蓋，方便測試重跑。"""
    if not spec.id or spec.id.strip() != spec.id:
        raise ValueError("組件 id 不可為空或含首尾空白")
    _REGISTRY[spec.id] = spec
    _STATUS.setdefault(spec.id, "enabled" if spec.enabled else "installed")
    return spec


def register_components(specs: tuple[ComponentSpec, ...] | list[ComponentSpec]) -> None:
    for spec in specs:
        register_component(spec)


def get_component(component_id: str) -> ComponentSpec | None:
    return _REGISTRY.get(component_id)


def list_components(*, include_disabled: bool = False) -> list[ComponentSpec]:
    specs = list(_REGISTRY.values())
    if include_disabled:
        return specs
    return [spec for spec in specs if spec.enabled]


def component_status(component_id: str) -> ComponentStatus:
    return _STATUS.get(component_id, "installed")


def component_reason(component_id: str) -> str:
    return _REASONS.get(component_id, "")


def _env_disabled_ids() -> set[str]:
    raw = os.getenv(DISABLED_ENV, "")
    return {part.strip() for part in raw.split(",") if part.strip()}


def resolve_order(specs: list[ComponentSpec]) -> list[ComponentSpec]:
    """依 ``requires`` 拓撲排序；同層維持宣告順序（穩定）。

    缺依賴的組件仍會回傳（供安裝器標記為 degraded），
    但依賴成環會拋 :class:`ComponentDependencyError`——那是宣告錯誤，不是執行期狀況。
    """
    by_id = {spec.id: spec for spec in specs}
    ordered: list[ComponentSpec] = []
    placed: set[str] = set()
    visiting: set[str] = set()

    def visit(spec: ComponentSpec, chain: tuple[str, ...]) -> None:
        if spec.id in placed:
            return
        if spec.id in visiting:
            raise ComponentDependencyError(
                "組件依賴成環：" + " → ".join((*chain, spec.id))
            )
        visiting.add(spec.id)
        for dep in spec.requires:
            target = by_id.get(dep)
            if target is not None:
                visit(target, (*chain, spec.id))
        visiting.discard(spec.id)
        if spec.id not in placed:
            placed.add(spec.id)
            ordered.append(spec)

    for spec in specs:
        visit(spec, ())
    return ordered


@dataclass
class InstalledComponents:
    """安裝結果：給 lifespan 排程掛鉤，也方便測試斷言。"""

    order: list[str] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)
    degraded: dict[str, str] = field(default_factory=dict)
    startup_hooks: list[Any] = field(default_factory=list)
    shutdown_hooks: list[Any] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "order": list(self.order),
            "skipped": dict(self.skipped),
            "degraded": dict(self.degraded),
            "startup_hooks": len(self.startup_hooks),
            "shutdown_hooks": len(self.shutdown_hooks),
        }


def install_components(app, specs: tuple[ComponentSpec, ...] | list[ComponentSpec]) -> InstalledComponents:
    """把組件安裝到 FastAPI 應用：掛路由、標記狀態、投影目錄。"""
    from backend.middleware.auth_gate import _OPEN_EXACT  # 只讀，用於驗證

    result = InstalledComponents()
    env_disabled = _env_disabled_ids()
    candidates = [spec for spec in specs if spec.enabled and spec.id not in env_disabled]

    for spec in specs:
        if not spec.enabled:
            _STATUS[spec.id] = "disabled"
            result.skipped[spec.id] = "declared_disabled"
        elif spec.id in env_disabled:
            _STATUS[spec.id] = "disabled"
            result.skipped[spec.id] = f"env:{DISABLED_ENV}"
            _REASONS[spec.id] = f"停用於 {DISABLED_ENV}"

    by_id = {spec.id: spec for spec in specs}
    for spec in resolve_order(candidates):
        missing = [dep for dep in spec.requires if dep not in by_id]
        if missing:
            _STATUS[spec.id] = "degraded"
            _REASONS[spec.id] = "缺少依賴：" + ", ".join(missing)
            result.degraded[spec.id] = _REASONS[spec.id]
            logger.warning("組件 %s 降級：%s", spec.id, _REASONS[spec.id])
        else:
            _STATUS[spec.id] = "enabled"

        if spec.router is not None:
            app.include_router(
                spec.router,
                include_in_schema=spec.include_in_schema,
            )
        result.order.append(spec.id)

        uncovered = [path for path in spec.gate_open_paths if path not in _OPEN_EXACT]
        if uncovered:
            logger.warning(
                "組件 %s 宣告的 gate_open_paths 未被 AuthGate 放行（需獨立 PR 修改）：%s",
                spec.id,
                ", ".join(uncovered),
            )

        if spec.on_startup is not None:
            result.startup_hooks.append(spec.on_startup)
        if spec.on_shutdown is not None:
            result.shutdown_hooks.append(spec.on_shutdown)

        if spec.is_catalog_exposed():
            register_module(spec.to_module_spec())

    return result


def component_manifest(
    specs: tuple[ComponentSpec, ...] | list[ComponentSpec] | None = None,
) -> dict[str, Any]:
    """產生前端讀取的 manifest（純函式，不落盤；落盤由匯出腳本負責）。

    未安裝的組件（例如只做宣告匯出時）狀態由 ``ComponentSpec.enabled`` 決定，
    不回報 ``installed``——那是安裝器的執行期狀態，不是宣告語義。
    """
    items = list(specs) if specs is not None else list(_REGISTRY.values())
    return {
        "schema_version": 1,
        "generated_from": "backend.modules.component_registry",
        "components": [
            spec.to_dict(status=_STATUS.get(spec.id)) for spec in items
        ],
    }
