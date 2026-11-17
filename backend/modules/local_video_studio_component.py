"""Local Video Studio 的組件宣告（組件化第一階段：只宣告，不改行為）。

與 ``media_vault_component`` 同一模式：沿用既有 ``build_local_video_studio_spec()``
與 ``backend.local_video_studio.api.router``，不新增路由、不改目錄輸出。
"""

from __future__ import annotations

from backend.modules.component import ComponentSpec, ComponentSurface, GuardRequirement
from backend.modules.local_video_studio import build_local_video_studio_spec

#: 既有 register.ts 註冊的頁鍵（projects／detail／shots／jobs／review／compose／
#: resources／home 全部指向同一 StudioHub，故掛載點共用一個 lazy_entry）。
_PAGES: tuple[tuple[str, str], ...] = (
    ("projects", "專案"),
    ("detail", "專案詳情"),
    ("shots", "鏡頭板"),
    ("jobs", "任務"),
    ("review", "審核"),
    ("compose", "合成"),
    ("resources", "資源"),
    ("home", "首頁"),
)

_SURFACES: tuple[ComponentSurface, ...] = tuple(
    ComponentSurface(
        mount="page",
        key=key,
        label=label,
        icon="▶",
        nav_group="studio",
        lazy_entry="modules/local-video-studio/register",
    )
    for key, label in _PAGES
)


def build_component() -> ComponentSpec:
    from backend.local_video_studio.api import router

    return ComponentSpec.from_module_spec(
        build_local_video_studio_spec(),
        surfaces=_SURFACES,
        router=router,
        guards=(
            GuardRequirement(
                kind="api_key",
                detail="寫入路由以 X-API-Key 依賴守門",
                enforced_by="backend.local_video_studio.api._require_api_key",
            ),
        ),
        # 全部能力都含寫入路由（建立專案／claim job／審核／合成…）。
        write_capability_ids=("projects", "shots", "jobs"),
        area="world",
    )
