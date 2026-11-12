"""伺服器運維智能體：健康快照、巡檢、日報與 LLM 規劃問答（自 backend.linkin.server_admin 抽出）。"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from backend.tools import server_admin as sa
from backend.tools.server_admin import ServerAdminError

from .config import _env_flag, _env_int, logger
from .pending import create_approval, list_approvals
from .tools import _KEYWORD_ROUTES, _SERVICE_HINTS, TOOL_CATALOG, execute_tool


def _package_attr(name: str) -> Any:
    """取套件 facade 的同名屬性；讓測試 monkeypatch `backend.linkin.server_admin.<name>` 生效。"""
    from backend.linkin import server_admin as _package

    return getattr(_package, name)


SA_SYSTEM_PROMPT = (
    "你是一個經驗豐富的 Linux 服務器運維專家（AIOps 智能體），管理著一台 Ubuntu 22.04 阿里雲服務器。"
    "你只能透過具名運維工具診斷與修復，絕不執行自由 shell 命令。"
    "破壞性操作（刪除、重啟、輪轉）由系統自動轉為人工批准，你不需要也不能自行確認。"
    "你的回答簡潔、專業，並附上關鍵監控指標數據。"
)


def health_snapshot() -> dict[str, Any]:
    """聚合讀操作：磁盤 + 系統負載 + Docker + 白名單服務 → 整體 ok/warn/critical。"""
    cfg = sa.load_config()
    checks: list[dict[str, Any]] = []
    disk = sa.get_disk_usage(config=cfg)
    checks.append({"name": "disk", "ok": disk.get("ok", False), "warning": bool(disk.get("warning")), "critical": float(disk.get("percent") or 0) >= 95, "detail": f"{disk.get('percent', '?')}% 已用（{disk.get('free_gb', '?')}GB 剩餘）"})
    load = sa.get_system_load(config=cfg)
    mem_pct = float((load.get("memory") or {}).get("percent") or 0)
    checks.append({"name": "system", "ok": load.get("ok", False), "warning": bool(load.get("warning")), "critical": mem_pct >= 95 or float(load.get("cpu_percent") or 0) >= 95, "detail": f"CPU {load.get('cpu_percent', '?')}% / 內存 {mem_pct}%"})
    docker = sa.get_docker_status(config=cfg)
    checks.append({"name": "docker", "ok": True, "warning": bool(docker.get("warning")), "critical": False, "detail": (f"{docker.get('running', 0)}/{docker.get('container_count', 0)} 容器運行中" if docker.get("available") else f"不可用（{docker.get('reason', '')[:60]}）")})
    for service in cfg.allow_services:
        try:
            svc = sa.check_service(service, config=cfg)
        except ServerAdminError:
            continue
        active = str(svc.get("active") or "")
        checks.append({
            "name": f"service:{service}",
            "ok": svc.get("ok", False),
            "warning": bool(svc.get("available")) and active not in {"active", "unknown"},
            "critical": bool(svc.get("available")) and active in {"failed", "inactive"},
            "detail": active if svc.get("available") else str(svc.get("reason") or "不可用")[:60],
        })
    status = "ok"
    if any(c["warning"] for c in checks):
        status = "warn"
    if any(c["critical"] for c in checks):
        status = "critical"
    return {"status": status, "dry_run": cfg.dry_run, "storage_root": str(cfg.storage_root), "checks": checks, "ts": time.time()}


def patrol(auto_approve: bool = False) -> dict[str, Any]:
    """主動巡檢：健康快照 + 規則引擎提案（清理/輪轉/重啟）→ 批准隊列或自動執行。"""
    snapshot = health_snapshot()
    cfg = sa.load_config()
    disk_warn = _env_int("EVOL_SA_DISK_WARN", 80, 10, 100)
    proposals: list[dict[str, Any]] = []
    disk_check = next((c for c in snapshot["checks"] if c["name"] == "disk"), None)
    disk_percent = 0.0
    if disk_check:
        match = re.match(r"([\d.]+)%", str(disk_check.get("detail") or ""))
        disk_percent = float(match.group(1)) if match else 0.0
    if disk_percent >= disk_warn:
        proposals.append({"tool": "clean_old_packages", "params": {"days": 7}, "reason": f"磁盤使用 {disk_percent}% ≥ 閾值 {disk_warn}%"})
        proposals.append({"tool": "clean_temp_files", "params": {"days": 3}, "reason": "磁盤偏高，順帶清理 temp"})
    for check in snapshot["checks"]:
        if check["name"].startswith("service:") and check.get("critical"):
            proposals.append({"tool": "restart_service", "params": {"name": check["name"].split(":", 1)[1]}, "reason": f"服務狀態：{check.get('detail')}"})
    try:
        rotate_preview = sa.rotate_logs(100, confirm=False, config=cfg)
        if int(rotate_preview.get("count") or 0) > 0:
            proposals.append({"tool": "rotate_logs", "params": {"max_mb": 100}, "reason": f"{rotate_preview.get('count')} 個日誌超過 100MB"})
    except ServerAdminError:
        pass

    outcomes: list[dict[str, Any]] = []
    auto = bool(auto_approve) and _env_flag("EVOL_SA_AUTO_APPROVE", False)
    for proposal in proposals:
        if auto:
            try:
                result = execute_tool(proposal["tool"], proposal["params"], confirm=True, role="patrol")
                outcomes.append({**proposal, "action": "auto_executed", "result": result})
                continue
            except ServerAdminError as exc:
                outcomes.append({**proposal, "action": "failed", "error": str(exc)})
                continue
        try:
            preview = execute_tool(proposal["tool"], proposal["params"], role="patrol")
            record = create_approval(proposal["tool"], proposal["params"], preview, question=f"巡檢提案：{proposal['reason']}")
            outcomes.append({**proposal, "action": "pending_approval", "approval_id": record["id"], "message": preview.get("message")})
        except ServerAdminError as exc:
            outcomes.append({**proposal, "action": "failed", "error": str(exc)})
    return {"status": snapshot["status"], "snapshot": snapshot, "proposals": outcomes, "auto_approved": auto, "ts": time.time()}


def audit_tail(limit: int = 100) -> list[dict[str, Any]]:
    """讀取運維審計日誌尾部（供 API / 日報統計）。"""
    cfg = sa.load_config()
    limit = max(1, min(int(limit), 1000))
    path = cfg.audit_path.expanduser()
    if not path.exists():
        return []
    try:
        with path.open("rb") as fh:
            size = path.stat().st_size
            if size > 512 * 1024:
                fh.seek(size - 512 * 1024)
                fh.readline()
            data = fh.read()
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    for line in data.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                rows.append(parsed)
        except json.JSONDecodeError:
            continue
    return rows[-limit:]


def daily_report() -> str:
    """產生 Markdown 日報：健康狀態 + 24h 審計統計 + 待批准項。"""
    snapshot = health_snapshot()
    cfg = sa.load_config()
    since = time.time() - 86400
    entries = [r for r in audit_tail(1000) if float(r.get("ts") or 0) >= since]
    by_tool: dict[str, int] = {}
    freed = 0
    for row in entries:
        tool = str(row.get("tool") or "?")
        by_tool[tool] = by_tool.get(tool, 0) + 1
        freed += int(row.get("freed") or 0)
    pending = [a for a in list_approvals() if a.get("status") == "pending"]
    icon = {"ok": "✅", "warn": "⚠️", "critical": "🔴"}.get(snapshot["status"], "❓")
    lines = [
        f"【服務器日報 - {time.strftime('%Y-%m-%d')}】",
        f"{icon} 整體狀態：{snapshot['status']}（{'乾跑模式' if cfg.dry_run else 'live 模式'}）",
    ]
    for check in snapshot["checks"]:
        mark = "🔴" if check.get("critical") else ("⚠️" if check.get("warning") else "✅")
        lines.append(f"{mark} {check['name']}: {check.get('detail', '')}")
    if by_tool:
        lines.append("🧾 24h 工具調用：" + "、".join(f"{k}×{v}" for k, v in sorted(by_tool.items(), key=lambda kv: kv[1], reverse=True)))
    else:
        lines.append("🧾 24h 工具調用：無")
    if freed:
        lines.append(f"🧹 24h 釋放空間：{freed / 1024**3:.2f}GB")
    lines.append(f"📋 待批准操作：{len(pending)} 項" + (f"（{', '.join(a['id'] for a in pending[:5])}）" if pending else ""))
    return "\n".join(lines)


def _llm_ready() -> bool:
    if _env_flag("EVOL_SA_NO_LLM", False):
        return False
    try:
        from backend.core.llm_config import get_runtime_config

        cfg = get_runtime_config()
        key = str(cfg.get("api_key") or os.getenv("OPENAI_API_KEY") or "").strip()
    except Exception:
        key = str(os.getenv("OPENAI_API_KEY") or "").strip()
    return bool(key) and not key.startswith("sk-your")


def _plan_with_llm(question: str) -> dict[str, Any] | None:
    catalog_text = "\n".join(
        f"- {name}: {info['desc']}；參數：{json.dumps(info['params'], ensure_ascii=False) or '無'}"
        for name, info in TOOL_CATALOG.items()
    )
    prompt = f"""【管理員問題】{question}
【可用工具】（只能選一個；寫工具標有【寫】，系統會自動轉人工批准，你不要自行確認）
{catalog_text}
【輸出】只輸出一個 JSON 物件，無其他文字：
{{"tool": "工具名", "params": {{...}}, "analysis": "一句話說明為什麼選這個工具與預期結果"}}
【規則】params 只填該工具文檔列出的鍵；服務名只能是：{'、'.join(sa.load_config().allow_services)}。"""
    model = os.getenv("EVOL_SA_MODEL", "").strip()
    if not model:
        from backend.core.stage_router import resolve_stage_model

        model = resolve_stage_model("generate", query=question)
    raw = _package_attr("call_llm")(prompt, system=SA_SYSTEM_PROMPT, model=model)
    data = _extract_json(raw or "")
    if not isinstance(data, dict):
        return None
    tool = str(data.get("tool") or "").strip()
    if tool not in TOOL_CATALOG:
        return None
    raw_params = data.get("params")
    params: dict[str, Any] = raw_params if isinstance(raw_params, dict) else {}
    return {"tool": tool, "params": _sanitize_params(tool, params), "analysis": str(data.get("analysis") or "")[:500], "planner": "llm", "model": str(model or "")}


def _extract_json(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", raw)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None


_PARAM_KEYS: dict[str, tuple[str, ...]] = {
    "get_disk_usage": ("target",),
    "check_service": ("name",),
    "analyze_disk_growth": ("days", "top"),
    "tail_log": ("name", "lines"),
    "clean_old_packages": ("days",),
    "clean_temp_files": ("days",),
    "rotate_logs": ("max_mb",),
    "restart_service": ("name",),
    "backup_incremental": ("subdir",),
}


_INT_PARAMS = frozenset({"days", "top", "lines", "max_mb"})


def _sanitize_params(tool: str, params: dict[str, Any]) -> dict[str, Any]:
    """只保留該工具文檔列出的鍵並做類型收斂（LLM 幻覺參數直接丟棄）。"""
    allowed = _PARAM_KEYS.get(tool, ())
    out: dict[str, Any] = {}
    for key in allowed:
        if key not in params:
            continue
        value = params[key]
        if key in _INT_PARAMS:
            try:
                out[key] = int(value)
            except (TypeError, ValueError):
                continue
        else:
            out[key] = str(value)[:200]
    return out


def _plan_keyword(question: str) -> dict[str, Any]:
    text = (question or "").lower()
    for tool, keywords, params in _KEYWORD_ROUTES:
        if any(kw in text for kw in keywords):
            plan_params = dict(params)
            if tool == "restart_service":
                name = next((s for s in _SERVICE_HINTS if s in text), "")
                cfg = sa.load_config()
                plan_params["name"] = next((s for s in cfg.allow_services if s in text or (s == "redis-server" and "redis" in text)), name)
            if tool == "check_service":
                cfg = sa.load_config()
                plan_params["name"] = next((s for s in cfg.allow_services if s in text or (s == "redis-server" and "redis" in text)), "")
            return {"tool": tool, "params": plan_params, "analysis": f"關鍵詞路由 → {tool}", "planner": "keyword"}
    return {"tool": "health", "params": {}, "analysis": "未命中具體工具，回整體健康快照", "planner": "keyword"}


def ask_agent(question: str, *, auto_approve: bool = False, role: str = "") -> dict[str, Any]:
    """自然語言運維問答入口：LLM 規劃（兜底關鍵詞）→ 讀即執行 / 寫轉批准。"""
    text = str(question or "").strip()
    if not text:
        raise ValueError("question 不可為空")
    plan: dict[str, Any] | None = None
    if _package_attr("_llm_ready")():
        try:
            plan = _plan_with_llm(text)
        except Exception as exc:
            logger.warning("運維 LLM 規劃失敗（降級關鍵詞路由）：%s", exc)
    if plan is None:
        plan = _plan_keyword(text)
    tool = plan["tool"]
    params = plan.get("params") or {}

    if tool == "health":
        snapshot = health_snapshot()
        return {"status": "ok", "question": text, "tool": "health", "analysis": plan.get("analysis", ""), "planner": plan.get("planner"), "result": snapshot}
    if tool == "patrol":
        report = patrol(auto_approve=auto_approve)
        return {"status": "ok", "question": text, "tool": "patrol", "analysis": plan.get("analysis", ""), "planner": plan.get("planner"), "result": report}
    if tool in sa.READONLY_TOOLS:
        result = execute_tool(tool, params, role=role)
        return {"status": "ok", "question": text, "tool": tool, "params": params, "analysis": plan.get("analysis", ""), "planner": plan.get("planner"), "result": result}
    # 寫工具：先無副作用預覽，再轉人工批准（或雙重開關自動執行）
    preview = execute_tool(tool, params, role=role)
    auto = bool(auto_approve) and _env_flag("EVOL_SA_AUTO_APPROVE", False)
    if auto:
        result = execute_tool(tool, params, confirm=True, role=role or "auto_approve")
        return {"status": "executed", "question": text, "tool": tool, "params": params, "analysis": plan.get("analysis", ""), "planner": plan.get("planner"), "result": result, "auto_approved": True}
    record = create_approval(tool, params, preview, question=text)
    return {
        "status": "pending_approval",
        "question": text,
        "tool": tool,
        "params": params,
        "analysis": plan.get("analysis", ""),
        "planner": plan.get("planner"),
        "approval_id": record["id"],
        "approval_required": True,
        "proposed_action": preview.get("message", ""),
        "preview": record["preview"],
        "expires_in_min": record["ttl_min"],
    }
