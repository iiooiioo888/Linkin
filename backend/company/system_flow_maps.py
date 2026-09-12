"""Linkin 系統架構／運作流程 → Archify IR（確定性，不經 LLM）。

對齊 docs/architecture/system-architecture-2026-09.md 與專題（共享池、積分池、RAHO、OPC）。
供 Lab → Archify 與 render_view(view=…) 使用。
"""

from __future__ import annotations

from typing import Any

from backend.company.quant_strategy_maps import ARCHIFY_SOURCE

_FLOW_CATALOG: tuple[dict[str, str], ...] = (
    {
        "id": "system-deploy",
        "title": "部署拓撲",
        "blurb": "Nginx → FastAPI → Redis／Chroma／OPC；Token Plan 與阿里雲 BSS 旁路。",
        "diagram_type": "architecture",
    },
    {
        "id": "langgraph",
        "title": "LangGraph 統一管線",
        "blurb": "retrieve → 上下文增強 → route_by_complexity → 公司／簡單 → 反思閉環 → save。",
        "diagram_type": "workflow",
    },
    {
        "id": "raho",
        "title": "RAHO 指揮鏈",
        "blurb": "L5 Grill-Me → L4 審計 → L3 戰術 → L2 執行 → L1 憲兵 → Reviewer → Synthesizer。",
        "diagram_type": "workflow",
    },
    {
        "id": "shared-pool",
        "title": "共享池掘礦",
        "blurb": "bind → 貢獻者 Key 優先路由 → settle → contribution_unlocked／fault_pool。",
        "diagram_type": "lifecycle",
    },
    {
        "id": "credit-pools",
        "title": "積分池生命週期",
        "blurb": "月贈／購買／貢獻池；預扣分級 reserve；鎖倉分期與 fault_pool。",
        "diagram_type": "lifecycle",
    },
    {
        "id": "opc",
        "title": "OPC 六級閉環",
        "blurb": "S1 感知 → P1 預處理 → A1 分析 → Dg1 診斷 → D1 決策 → A2 執行（WriteGuard）。",
        "diagram_type": "workflow",
    },
    {
        "id": "evoloop",
        "title": "EvoLoop 總覽",
        "blurb": "前端 → API → 路由 → LangGraph／公司運行時／OPC → LiteLLM 與記憶。",
        "diagram_type": "architecture",
        "legacy": "true",
    },
)

_LEGACY_ALIASES = {"system": "evoloop"}


def _ir(
    title: str,
    kind: str,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    *,
    lanes: list[dict[str, str]] | None = None,
    extra_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "title": title,
        "type": kind,
        "locale": "zh-TW",
        "source": "archify",
        "inspired_by": ARCHIFY_SOURCE,
        "visual_preset": "signal-flow",
    }
    if extra_meta:
        meta.update(extra_meta)
    payload: dict[str, Any] = {"meta": meta, "nodes": nodes, "edges": edges}
    if lanes:
        payload["lanes"] = lanes
    return payload


def _node(
    nid: str,
    label: str,
    role: str,
    *,
    status: str = "",
    lane: str = "",
    detail: str = "",
) -> dict[str, Any]:
    row: dict[str, Any] = {"id": nid, "label": label, "role": role}
    if status:
        row["status"] = status
    if lane:
        row["lane"] = lane
    if detail:
        row["detail"] = detail
    return row


def _edge(src: str, dst: str, label: str = "") -> dict[str, Any]:
    row: dict[str, Any] = {"from": src, "to": dst}
    if label:
        row["label"] = label
    return row


def deploy_topology_ir() -> dict[str, Any]:
    """生產部署：Nginx → API → Redis/OPC/Chroma；Token Plan 與 BSS。"""
    nodes = [
        _node("nginx", "Nginx :80", "frontend", detail="TLS·靜態·反代"),
        _node("api", "FastAPI :8000", "api", detail="LangGraph·計費·Hub"),
        _node("redis", "Redis", "data", detail="任務·會話·快取"),
        _node("chroma", "ChromaDB", "data", detail="向量記憶"),
        _node("opc", "OPC :18000", "service", detail="guard 寫入護欄"),
        _node("token_plan", "Token Plan", "service", detail="plans.py 權益"),
        _node("llm", "LiteLLM", "external", detail="多供應商路由"),
        _node("bss", "阿里雲 BSS", "external", detail="雲帳單 OpenAPI"),
        _node("docker", "Docker 計費", "cloud", detail="按時扣 purchased"),
    ]
    edges = [
        _edge("nginx", "api", "/api·/chat"),
        _edge("api", "redis", "TaskManager"),
        _edge("api", "chroma", "記憶 R/W"),
        _edge("api", "opc", "工業閉環"),
        _edge("api", "llm", "call_llm"),
        _edge("api", "token_plan", "方案·預扣"),
        _edge("api", "bss", "Agent 預算"),
        _edge("api", "docker", "容器用量"),
    ]
    return _ir("Linkin 部署拓撲", "architecture", nodes, edges, extra_meta={"view": "system-deploy"})


def langgraph_pipeline_ir() -> dict[str, Any]:
    """統一管線：retrieve → enhance* → route → company/simple → 反思閉環。"""
    lanes = [
        {"id": "ingress", "label": "上下文"},
        {"id": "route", "label": "路由"},
        {"id": "exec", "label": "執行"},
        {"id": "loop", "label": "反思閉環"},
    ]
    nodes = [
        _node("retrieve", "retrieve_memories", "data", lane="ingress", detail="Chroma 檢索"),
        _node("opc_ctx", "enhance_opc", "service", lane="ingress"),
        _node("linkin_ctx", "enhance_linkin", "service", lane="ingress"),
        _node("recall_ctx", "enhance_recall", "service", lane="ingress"),
        _node("route", "route_by_complexity", "api", lane="route"),
        _node("company", "run_company", "service", lane="exec", detail="85 席·RAHO"),
        _node("simple", "generate_initial", "service", lane="exec", detail="單次 LLM"),
        _node("enforce", "enforce_length", "api", lane="loop"),
        _node("evaluate", "evaluate_answer", "service", lane="loop"),
        _node("reflect", "reflect→improve", "service", lane="loop"),
        _node("save", "save_memory", "data", lane="loop"),
        _node("archive", "archive_state", "api", lane="loop", status="END"),
    ]
    edges = [
        _edge("retrieve", "opc_ctx"),
        _edge("opc_ctx", "linkin_ctx"),
        _edge("linkin_ctx", "recall_ctx"),
        _edge("recall_ctx", "route"),
        _edge("route", "company", "複雜"),
        _edge("route", "simple", "簡單"),
        _edge("company", "enforce"),
        _edge("simple", "enforce"),
        _edge("enforce", "evaluate"),
        _edge("evaluate", "reflect", "未達門檻"),
        _edge("reflect", "enforce", "improve"),
        _edge("evaluate", "save", "finalize"),
        _edge("save", "archive"),
    ]
    return _ir(
        "LangGraph 統一管線",
        "workflow",
        nodes,
        edges,
        lanes=lanes,
        extra_meta={"view": "langgraph"},
    )


def raho_spine_ir() -> dict[str, Any]:
    """RAHO 指揮鏈 + 獨立審查 + 收斂合成。"""
    lanes = [
        {"id": "command", "label": "指揮鏈"},
        {"id": "inspect", "label": "獨立審查"},
        {"id": "out", "label": "交付"},
    ]
    nodes = [
        _node("l5", "L5 Grill-Me", "frontend", lane="command", detail="語意鎖定"),
        _node("l4", "L4 需求審計", "api", lane="command", detail="戰役 DAG"),
        _node("l3", "L3 戰術指揮", "service", lane="command", detail="原子拆解"),
        _node("l2", "L2 執行", "service", lane="command", detail="ReAct tool"),
        _node("l1", "L1 憲兵", "security", lane="inspect", detail="InspectorGate"),
        _node("review", "Reviewer", "service", lane="out", detail="品質驗收"),
        _node("synth", "Synthesizer", "api", lane="out", detail="最終合成"),
    ]
    edges = [
        _edge("l5", "l4", "[GRILL]"),
        _edge("l4", "l3"),
        _edge("l3", "l2"),
        _edge("l2", "l1"),
        _edge("l1", "review"),
        _edge("review", "synth"),
    ]
    return _ir("RAHO 指揮鏈", "workflow", nodes, edges, lanes=lanes, extra_meta={"view": "raho"})


def shared_pool_mining_ir() -> dict[str, Any]:
    """共享池：bind → 貢獻者優先路由 → settle → 獎勵／平台抽成。"""
    nodes = [
        _node("bind", "select_and_bind", "api", detail="task_key_binding"),
        _node("route", "sort_keys", "service", detail="貢獻者>platform"),
        _node("call", "call_llm", "external", detail="in_use"),
        _node("settle", "settle_task", "service", detail="tokens·cost"),
        _node("reward", "contribution_unlocked", "data", status="catalog", detail="掘礦入帳"),
        _node("fault", "fault_pool", "data", status="catalog", detail="platform_take"),
        _node("failover", "failover", "frontend", status="block", detail="429·5xx"),
    ]
    edges = [
        _edge("bind", "route"),
        _edge("route", "call", "healthy"),
        _edge("call", "settle"),
        _edge("settle", "reward", "貢獻者 Key"),
        _edge("settle", "fault", "抽成"),
        _edge("call", "failover", "key_failure"),
        _edge("failover", "route", "重路由"),
    ]
    return _ir(
        "共享池掘礦",
        "lifecycle",
        nodes,
        edges,
        extra_meta={"view": "shared-pool"},
    )


def credit_pools_lifecycle_ir() -> dict[str, Any]:
    """計費 v6 多池：月贈→購買→預扣→結算；貢獻池鎖倉與 fault。"""
    nodes = [
        _node("grant", "monthly_grant", "data", detail="Token Plan 月贈"),
        _node("purchased", "purchased", "data", detail="充值·退還"),
        _node("unlocked", "contrib_unlocked", "service", detail="掘礦·1:0.4"),
        _node("locked", "contrib_locked", "security", detail="30/90/180 天"),
        _node("reserve", "reserve_for_task", "api", detail="50%·100% 分級"),
        _node("settle", "finalize_task", "service", detail="補扣·退還"),
        _node("fault", "fault_pool", "data", status="catalog", detail="違約·平台池"),
    ]
    edges = [
        _edge("grant", "reserve", "SPEND_ORDER"),
        _edge("purchased", "reserve"),
        _edge("unlocked", "locked", "lock_contrib"),
        _edge("locked", "purchased", "分期解鎖"),
        _edge("unlocked", "purchased", "convert×0.4"),
        _edge("reserve", "settle"),
        _edge("locked", "fault", "early_unlock"),
    ]
    return _ir(
        "積分池生命週期",
        "lifecycle",
        nodes,
        edges,
        extra_meta={"view": "credit-pools"},
    )


def opc_six_stage_ir() -> dict[str, Any]:
    """OPC 六級：S1→P1→A1→Dg1→D1→A2，寫入經 WriteGuard。"""
    lanes = [{"id": "pipeline", "label": "opc_service 閉環"}]
    nodes = [
        _node("s1", "S1 感知", "data", lane="pipeline", detail="sense_opc"),
        _node("p1", "P1 預處理", "service", lane="pipeline"),
        _node("a1", "A1 分析", "service", lane="pipeline"),
        _node("dg1", "Dg1 診斷", "external", lane="pipeline", detail="LLM 根因"),
        _node("d1", "D1 決策", "api", lane="pipeline"),
        _node("guard", "WriteGuard", "security", lane="pipeline", detail="白名單·邊界"),
        _node("a2", "A2 執行", "service", lane="pipeline", detail="act_opc"),
    ]
    edges = [
        _edge("s1", "p1"),
        _edge("p1", "a1"),
        _edge("a1", "dg1"),
        _edge("dg1", "d1"),
        _edge("d1", "guard"),
        _edge("guard", "a2", "validate"),
    ]
    return _ir("OPC 六級閉環", "workflow", nodes, edges, lanes=lanes, extra_meta={"view": "opc"})


_FLOW_BUILDERS: dict[str, Any] = {
    "system-deploy": deploy_topology_ir,
    "langgraph": langgraph_pipeline_ir,
    "raho": raho_spine_ir,
    "shared-pool": shared_pool_mining_ir,
    "credit-pools": credit_pools_lifecycle_ir,
    "opc": opc_six_stage_ir,
}


def system_flow_catalog() -> dict[str, Any]:
    """Lab UI 用：可選系統流程清單。"""
    flows = []
    for row in _FLOW_CATALOG:
        entry = dict(row)
        entry["legacy"] = entry.get("legacy") == "true"
        flows.append(entry)
    return {
        "ok": True,
        "source": ARCHIFY_SOURCE,
        "flows": flows,
        "default_view": "langgraph",
        "hint": "GET /lab/archify/html?view=<id> 或 ArchifyFrame view=…",
    }


def resolve_system_flow_ir(view: str) -> dict[str, Any]:
    """依 view id 回傳簡化 IR；evoloop/system 走 lab_tools 內建圖。"""
    key = (view or "").strip().lower()
    key = _LEGACY_ALIASES.get(key, key)
    if key in {"evoloop", "system"}:
        from backend.services.lab_tools import get_evoloop_architecture

        ir = get_evoloop_architecture()
        ir.setdefault("meta", {})["view"] = "evoloop"
        return ir
    builder = _FLOW_BUILDERS.get(key)
    if builder is None:
        allowed = sorted(set(_FLOW_BUILDERS) | {"evoloop", "system"})
        raise ValueError(f"未知系統流程 view={view!r}。可用：{', '.join(allowed)}")
    return builder()


def list_system_flow_ids() -> tuple[str, ...]:
    return tuple(row["id"] for row in _FLOW_CATALOG)
