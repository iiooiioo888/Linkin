"""監控中心 API：控制面版聚合、OPC／Hub／Agent 監控、角色設定與席位投遞餵給。

自 backend.main 抽出；端點行為、模型與回應結構不變。
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.company.role_catalog import (
    create_custom_role,
    delete_custom_role,
    reset_role_settings,
    update_monitor_prefs,
    update_role_settings,
)
from backend.company.seat_io import STORE
from backend.hub.monitor import collect_hub_monitor
from backend.services.agent_monitor import collect_agent_monitor
from backend.services.dashboard import collect_dashboard
from backend.services.opc_monitor import collect_opc_monitor
from backend.tenant.http import require_tenant_http

router = APIRouter(tags=["monitor"])


@router.get("/dashboard")
async def dashboard():
    """控制面版聚合資料：統計/任務/存檔/OPC 審計/能力註冊表。"""
    return collect_dashboard()


@router.get("/monitor/opc")
async def monitor_opc():
    """監控中心 OPC 分頁：護欄、審計、即時標籤、最近 6 級任務。"""
    return collect_opc_monitor()


@router.get("/monitor/hub")
async def monitor_hub():
    """監控中心 AI Hub 分頁：探針、熔斷、呼叫日誌、預算。"""
    return collect_hub_monitor()


class RoleSettingsBody(BaseModel):
    enabled: bool | None = None
    name: str | None = None
    system_prompt: str | None = None
    responsibilities: list[str] | None = None
    default_tier: str | None = None
    max_parallel_work: int | None = None
    preferred_model: str | None = None
    preferred_provider: str | None = None
    daily_budget_usd: float | None = None
    weekly_budget_usd: float | None = None
    monthly_budget_usd: float | None = None
    cloud_daily_budget_usd: float | None = None
    cloud_weekly_budget_usd: float | None = None
    cloud_monthly_budget_usd: float | None = None
    tools_allowed: list[str] | None = None
    notes: str | None = None
    reporting_to: str | None = None
    can_delegate_to: list[str] | None = None
    alert_on_error: bool | None = None
    alert_on_budget: bool | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None
    timeout_ms: int | None = None
    routing_strategy: str | None = None
    failover_models: list[str] | None = None
    sla_latency_ms: int | None = None
    max_retries: int | None = None
    alert_on_sla: bool | None = None
    level: int | None = None
    category: str | None = None
    language: str | None = None
    always_require_review: bool | None = None
    priority: int | None = None
    description: str | None = None
    max_daily_items: int | None = None
    require_human_approval: bool | None = None
    stream_enabled: bool | None = None
    cache_enabled: bool | None = None
    pii_redact: bool | None = None
    mainland_only: bool | None = None
    heartbeat_sec: int | None = None
    on_call: bool | None = None
    tags: list[str] | None = None
    notify_channel: str | None = None
    quiet_hours: str | None = None
    context_window: int | None = None
    allow_tool_use: bool | None = None
    auto_escalate: bool | None = None


class CustomRoleBody(BaseModel):
    id: str = ""
    name: str
    clone_from: str | None = None
    level: int = 3
    category: str = "management"
    reporting_to: str | None = None
    can_delegate_to: list[str] = []
    responsibilities: list[str] = []
    system_prompt: str = ""
    max_parallel_work: int = 2
    default_tier: str = "routine"
    preferred_model: str = ""
    preferred_provider: str = ""
    daily_budget_usd: float = 0
    weekly_budget_usd: float = 0
    monthly_budget_usd: float = 0
    cloud_daily_budget_usd: float = 0
    cloud_weekly_budget_usd: float = 0
    cloud_monthly_budget_usd: float = 0
    tools_allowed: list[str] = []
    notes: str = ""
    enabled: bool = True
    alert_on_error: bool = True
    alert_on_budget: bool = True
    alert_on_sla: bool = True
    temperature: float = 0.7
    max_output_tokens: int = 4096
    timeout_ms: int = 120000
    routing_strategy: str = "quality_first"
    failover_models: list[str] = []
    sla_latency_ms: int = 0
    max_retries: int = 3
    language: str = "zh-TW"
    always_require_review: bool = False
    priority: int = 3
    description: str = ""
    max_daily_items: int = 0
    require_human_approval: bool = False
    stream_enabled: bool = True
    cache_enabled: bool = True
    pii_redact: bool = True
    mainland_only: bool = False
    heartbeat_sec: int = 0
    on_call: bool = False
    tags: list[str] = []
    notify_channel: str = ""
    quiet_hours: str = ""
    context_window: int = 0
    allow_tool_use: bool = True
    auto_escalate: bool = True


class MonitorPrefsBody(BaseModel):
    poll_interval_ms: int | None = None
    show_disabled: bool | None = None
    show_idle: bool | None = None
    show_custom_only: bool | None = None
    group_by: str | None = None
    compact_cards: bool | None = None
    default_desk_tab: str | None = None
    sort_by: str | None = None
    capacity_warn_pct: int | None = None
    show_prompt_preview: bool | None = None
    highlight_alerts: bool | None = None
    auto_open_busy: bool | None = None
    default_layout: str | None = None
    sound_on_alert: bool | None = None
    show_cost_in_cards: bool | None = None
    pin_role_ids: list[str] | None = None
    filter_min_level: int | None = None
    filter_max_level: int | None = None
    timezone: str | None = None
    show_on_call_only: bool | None = None


@router.get("/monitor/agents")
async def monitor_agents():
    """監控中心角色 Agent：每位公司角色獨立任務列表與監控。"""
    return collect_agent_monitor()


@router.put("/monitor/agents/prefs")
async def monitor_agents_prefs(body: MonitorPrefsBody):
    """更新角色監控顯示偏好（輪詢間隔、是否顯示停用／待命）。"""
    require_tenant_http()
    try:
        return update_monitor_prefs(body.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/monitor/agents/{role_id}/settings")
async def monitor_agent_settings(role_id: str, body: RoleSettingsBody):
    """更新指定角色的設定（提示詞、模型、預算、啟用狀態）。"""
    require_tenant_http()
    try:
        return update_role_settings(role_id, body.model_dump(exclude_none=True))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/monitor/agents/{role_id}/reset")
async def monitor_agent_reset(role_id: str):
    """還原內建角色設定為系統預設。"""
    require_tenant_http()
    try:
        return reset_role_settings(role_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/monitor/agents")
async def monitor_agents_create(body: CustomRoleBody):
    """新增自定義角色（出現在監控中心，可編輯完整角色設定）。"""
    require_tenant_http()
    try:
        return create_custom_role(body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/monitor/agents/{role_id}")
async def monitor_agents_delete(role_id: str):
    """刪除自定義角色。內建角色不可刪，請改為停用。"""
    require_tenant_http()
    try:
        delete_custom_role(role_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "id": role_id}


# ==================== 公司運行時：席位 I/O 監察餵給 API ====================

_SEAT_TEXT_FIELDS = ("system", "prompt", "response")


def _seat_row_light(row: dict) -> dict:
    """列表用輕量投影：正文換成預覽＋長度，單條全文另取。"""
    light = {k: v for k, v in row.items() if k not in _SEAT_TEXT_FIELDS}
    for field in _SEAT_TEXT_FIELDS:
        text = str(row.get(field) or "")
        light[f"{field}_preview"] = text[:320]
        light[f"{field}_length"] = int(row.get(f"{field}_length") or len(text))
    return light


@router.get("/monitor/raho/feed")
def raho_seat_feed(
    task_id: str = "",
    run_id: str = "",
    role: str = "",
    layer: int | None = None,
    item_id: str = "",
    kind: str = "",
    limit: int = 120,
    full: bool = False,
):
    """席位投遞餵給：公司模式監察頁的單一資料源。

    每一筆 = 一次真正投遞給模型的調用（含重試與工具閉環的逐輪）。
    預設回傳輕量投影（正文僅預覽）；full=true 或走單條端點取全文。
    環形緩衝查不到時，自動回退到持久 seat_<run_id>.jsonl（跨重啟可查）。
    """
    rows = STORE.list(
        run_id=run_id,
        task_id=task_id,
        role=role,
        layer=layer,
        item_id=item_id,
        limit=limit,
    )
    source = "memory"
    if not rows and run_id:
        rows = STORE.load_run(run_id, limit=limit)
        source = "disk"
    if kind:
        rows = [r for r in rows if r.get("kind") == kind]
    return {
        "items": rows if full else [_seat_row_light(r) for r in rows],
        "source": source,
        "runs": STORE.recent_runs(limit=20),
        "total_roles": len({r.get("role") for r in rows if r.get("role")}),
    }


@router.get("/monitor/raho/seat/{io_id}")
def raho_seat_detail(io_id: str):
    """單次席位投遞全文（系統提示詞／組裝 prompt／模型回應／來源分解）。"""
    row = STORE.get(io_id)
    if row is None:
        raise HTTPException(status_code=404, detail="投遞軌跡不存在")
    return row
