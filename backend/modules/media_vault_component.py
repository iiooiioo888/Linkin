"""Media Vault 的組件宣告（組件化第一階段：只宣告，不改行為）。

本模組**不新增路由、不改目錄輸出**——``build_component()`` 直接沿用
既有 ``build_media_vault_spec()`` 與 ``backend.media_vault.api.router``，
經 :meth:`ComponentSpec.from_module_spec` 轉成組件宣告。
``GET /modules`` 的內容仍由 ``backend.modules.media_vault`` 提供（B1 才切換）。
"""

from __future__ import annotations

from backend.modules.component import (
    ComponentSpec,
    ComponentSurface,
    GuardRequirement,
)
from backend.modules.media_vault import build_media_vault_spec

_PREFIX = "/media-vault"

#: 面板鍵 → 前端掛載點。media-vault 是整頁型模組，三個面板同屬一頁。
_SURFACES: tuple[ComponentSurface, ...] = (
    ComponentSurface(
        mount="page",
        key="control",
        label="控制",
        icon="⎈",
        hint="採集任務與入庫",
        nav_group="panels",
        capability="control",
        lazy_entry="modules/media-vault/register",
        aliases=("展示",),
    ),
    ComponentSurface(
        mount="page",
        key="gallery",
        label="图库",
        icon="▦",
        hint="篩選、網格與燈箱",
        nav_group="panels",
        capability="gallery",
        lazy_entry="modules/media-vault/register",
        aliases=("展示",),
    ),
    ComponentSurface(
        mount="page",
        key="monitor",
        label="監控",
        icon="◉",
        hint="成功率、合規與儲存",
        nav_group="panels",
        capability="monitor",
        lazy_entry="modules/media-vault/register",
    ),
)


def build_component() -> ComponentSpec:
    from backend.media_vault.api import router

    return ComponentSpec.from_module_spec(
        build_media_vault_spec(),
        surfaces=_SURFACES,
        router=router,
        guards=(
            # 媒體庫沒有專屬寫入護欄，寫入僅受全域會話閘約束（既有事實，B0 不改）。
            GuardRequirement(
                kind="auth",
                detail="/ingest/replay 僅受會話閘門約束，尚無模組級寫入白名單",
                enforced_by="backend.middleware.auth_gate.AuthGateMiddleware",
            ),
        ),
        # /ingest/replay 會寫入媒資庫（觸發 ingest），屬寫入能力。
        write_capability_ids=("control",),
        area="world",
    )
