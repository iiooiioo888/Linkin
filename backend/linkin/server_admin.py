"""靈境·服務器運維域層：具名工具編排、人工批准隊列與 LLM 運維智能體（AIOps）。

三層模式對照 Minecraft MCP（AGENTS.md 鐵律）：
    backend/tools/server_admin.py   底層橋接（psutil/docker/systemd + 護欄 + 乾跑 + 審計）
    backend/linkin/server_admin.py  本檔：批准隊列、LLM 規劃、巡檢、日報、公司工具掛載
    backend/linkin/api.py           REST：/linkin/server/*

核心紀律：
- **絕不暴露自由 shell**——只有具名工具白名單（底層 ALL_TOOLS）
- 寫操作一律先產生 ``pending_approval``，管理員確認後才執行；
  ``auto_approve`` 需要環境變數 ``EVOL_SA_AUTO_APPROVE=true`` 雙重開關才生效
- LLM 經 backend.core.llm.call_llm（AGENTS.md #1）；無金鑰/失敗時降級關鍵詞路由
- 批准隊列 JSON 持久化（EVOL_SA_PENDING_PATH），TTL 過期自動作廢

環境變數：
    EVOL_SA_PENDING_PATH      批准隊列路徑（默認 backend/data/linkin/server_pending.json）
    EVOL_SA_PENDING_TTL_MIN   批准有效期分鐘（默認 30，1–1440）
    EVOL_SA_AUTO_APPROVE      允許 API 的 auto_approve 直接執行（默認 false）
    EVOL_SA_NO_LLM            強制關閉 LLM 規劃（關鍵詞路由兜底）
    EVOL_SA_MODEL             規劃模型（默認走 stage_router 的 generate 層級）
    EVOL_SA_DISK_WARN         巡檢磁盤告警閾值 %（默認 80）
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from backend.core.llm import call_llm
from backend.tools import server_admin as sa
from backend.tools.server_admin import ServerAdminError

logger = logging.getLogger(__name__)

_TRUE = {"1", "true", "yes", "on", "y"}
DEFAULT_PENDING_PATH = Path("backend/data/linkin/server_pending.json")
DEFAULT_TTL_MIN = 30
PENDING_KEEP_DAYS = 7  # 已完成記錄保留天數（防止文件膨脹）

SA_SYSTEM_PROMPT = (
    "你是一個經驗豐富的 Linux 服務器運維專家（AIOps 智能體），管理著一台 Ubuntu 22.04 阿里雲服務器。"
    "你只能透過具名運維工具診斷與修復，絕不執行自由 shell 命令。"
    "破壞性操作（刪除、重啟、輪轉）由系統自動轉為人工批准，你不需要也不能自行確認。"
    "你的回答簡潔、專業，並附上關鍵監控指標數據。"
)

# LLM 規劃目錄：工具 → (說明, 參數說明)。health 為聚合偽工具。
TOOL_CATALOG: dict[str, dict[str, Any]] = {
    "health": {"desc": "整體健康快照（磁盤/CPU/內存/Docker/白名單服務）", "params": {}},
    "patrol": {"desc": "主動巡檢：健康快照 + 規則提案（清理/輪轉/重啟自動轉人工批准）", "params": {}},
    "get_disk_usage": {"desc": "磁盤使用率（存儲根或子目錄）", "params": {"target": "可選子目錄，如 packages"}},
    "get_system_load": {"desc": "CPU / 內存 / load average", "params": {}},
    "get_memory_usage": {"desc": "內存使用", "params": {}},
    "get_docker_status": {"desc": "所有 Docker 容器狀態", "params": {}},
    "check_service": {"desc": "查詢 systemd 服務狀態（白名單內）", "params": {"name": "服務名，如 mysql"}},
    "analyze_disk_growth": {"desc": "磁盤增長分析：各目錄佔用、近 N 天增長來源、最大新文件", "params": {"days": "窗口天數(1-365)", "top": "返回條數(1-50)"}},
    "tail_log": {"desc": "讀日誌尾部（logs/ 內文件或 audit）", "params": {"name": "日誌文件名或 audit", "lines": "行數(1-1000)"}},
    "clean_old_packages": {"desc": "【寫】清理 packages/ 超過 N 天的 .zip", "params": {"days": "天數(默認7)"}},
    "clean_temp_files": {"desc": "【寫】清理 temp/ 超過 N 天的文件", "params": {"days": "天數(默認3)"}},
    "rotate_logs": {"desc": "【寫】gzip 輪轉 logs/ 超過 N MB 的 .log", "params": {"max_mb": "MB 閾值(默認100)"}},
    "restart_service": {"desc": "【寫】重啟白名單 systemd 服務", "params": {"name": "服務名"}},
    "backup_incremental": {"desc": "【寫】增量備份 assets/schematics 等到備份目錄", "params": {"subdir": "子目錄(默認assets)"}},
}

# 關鍵詞路由（無 LLM 時的兜底；順序即優先級）
_KEYWORD_ROUTES: tuple[tuple[str, tuple[str, ...], dict[str, Any]], ...] = (
    ("patrol", ("巡檢", "巡检", "自動清理", "自动清理", "自動修復", "自动修复", "全面檢查", "全面检查", "體檢", "体检"), {}),
    ("clean_old_packages", ("zip", "打包", "舊包", "旧包", "過期包", "过期包"), {"days": 7}),
    ("clean_temp_files", ("temp", "臨時", "临时", "緩存文件", "缓存文件", "python 緩存", "python 缓存", "pyc"), {"days": 3}),
    ("rotate_logs", ("輪轉", "轮转", "rotate", "日誌太大", "日志太大", "log 太大"), {"max_mb": 100}),
    ("backup_incremental", ("備份", "备份", "backup", "歸檔", "归档"), {"subdir": "assets"}),
    ("restart_service", ("重啟", "重启", "restart", "崩潰", "崩溃", "掛了", "挂了", "down"), {}),
    ("analyze_disk_growth", ("為什麼漲", "为什么涨", "涨得", "漲得", "增長", "增长", "佔用最多", "占用最多", "什麼占", "什么占", "哪個目錄", "哪个目录", "磁盤", "磁盘", "disk", "空間不足", "空间不足", "快滿", "快满"), {"days": 7}),
    ("tail_log", ("日誌", "日志", "log", "報錯", "报错"), {"name": "app", "lines": 100}),
    ("get_docker_status", ("docker", "容器", "container"), {}),
    ("get_system_load", ("cpu", "內存", "内存", "memory", "負載", "负载", "load", "性能"), {}),
    ("check_service", ("mysql", "redis", "nginx", "服務狀態", "服务状态", "連接數", "连接数"), {}),
)

_SERVICE_HINTS = ("linkin-api", "mysql", "redis-server", "redis", "nginx")

_lock = threading.RLock()
_pending_cache: dict[str, Any] | None = None
_pending_mtime: float | None = None


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in _TRUE


def _env_int(name: str, default: int, lo: int, hi: int) -> int:
    try:
        value = int(os.getenv(name, "").strip())
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, value))


def reset_cache() -> None:
    """清空批准隊列的模組級快取（測試隔離用）。"""
    global _pending_cache, _pending_mtime
    with _lock:
        _pending_cache = None
        _pending_mtime = None


def pending_path() -> Path:
    raw = os.getenv("EVOL_SA_PENDING_PATH", "").strip()
    return Path(raw).expanduser() if raw else DEFAULT_PENDING_PATH


def _load_pending() -> dict[str, Any]:
    global _pending_cache, _pending_mtime
    path = pending_path()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = None
    if _pending_cache is not None and _pending_mtime == mtime:
        return _pending_cache
    store: dict[str, Any] = {"approvals": []}
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and isinstance(raw.get("approvals"), list):
                store["approvals"] = [a for a in raw["approvals"] if isinstance(a, dict)]
        except (OSError, json.JSONDecodeError):
            logger.warning("讀取批准隊列失敗，改用空隊列：%s", path)
    _pending_cache = store
    _pending_mtime = mtime
    return store


def _save_pending(store: dict[str, Any]) -> None:
    global _pending_cache, _pending_mtime
    cutoff = time.time() - PENDING_KEEP_DAYS * 86400
    store["approvals"] = [
        a for a in store.get("approvals", [])
        if a.get("status") == "pending" or float(a.get("created_ts") or 0) >= cutoff
    ][-500:]
    path = pending_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(store, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)
    _pending_cache = store
    try:
        _pending_mtime = path.stat().st_mtime
    except OSError:
        _pending_mtime = None


def _ttl_min() -> int:
    return _env_int("EVOL_SA_PENDING_TTL_MIN", DEFAULT_TTL_MIN, 1, 1440)


def _is_expired(record: dict[str, Any]) -> bool:
    if record.get("status") != "pending":
        return False
    deadline = float(record.get("created_ts") or 0) + float(record.get("ttl_min") or DEFAULT_TTL_MIN) * 60
    return time.time() > deadline


# ── 批准隊列 ──


def create_approval(tool: str, params: dict[str, Any], preview: dict[str, Any], question: str = "") -> dict[str, Any]:
    """為寫操作建立待批准記錄（含無副作用的預覽掃描結果）。"""
    record = {
        "id": f"sa-{uuid.uuid4().hex[:10]}",
        "tool": tool,
        "params": params,
        "question": question[:300],
        "preview": {k: preview.get(k) for k in ("message", "count", "bytes", "days", "max_mb", "service", "subdir") if k in preview},
        "status": "pending",
        "created_ts": time.time(),
        "ttl_min": _ttl_min(),
        "resolved_ts": None,
        "result": None,
    }
    with _lock:
        store = dict(_load_pending())
        store["approvals"] = [*store.get("approvals", []), record]
        _save_pending(store)
    return record


def list_approvals(include_done: bool = False) -> list[dict[str, Any]]:
    with _lock:
        store = _load_pending()
        approvals = store.get("approvals", [])
        out: list[dict[str, Any]] = []
        changed = False
        for index, record in enumerate(approvals):
            if _is_expired(record):
                record = {**record, "status": "expired"}
                approvals[index] = record
                changed = True
            if record["status"] == "pending" or include_done:
                out.append(record)
        if changed:
            _save_pending(store)
        return out


def _get_pending_or_raise(approval_id: str) -> dict[str, Any]:
    with _lock:
        store = _load_pending()
        for record in store.get("approvals", []):
            if record.get("id") == approval_id:
                if _is_expired(record):
                    record["status"] = "expired"
                    record["resolved_ts"] = time.time()
                    _save_pending(store)
                    raise ServerAdminError("批准請求已過期，請重新發起", code="expired", extra={"id": approval_id})
                return record
    raise LookupError(f"批准請求不存在：{approval_id}")


def confirm_approval(approval_id: str) -> dict[str, Any]:
    """管理員批准 → 以 confirmed=True 執行寫工具 → 記錄結果。"""
    with _lock:
        store = _load_pending()
        record = _get_pending_or_raise(approval_id)
        if record["status"] != "pending":
            raise ServerAdminError(
                f"批准請求狀態為 {record['status']}，不可重複確認",
                code="invalid_state",
                extra={"id": approval_id, "status": record["status"]},
            )
        try:
            result = sa.execute_named_tool(record["tool"], record["params"], confirm=True)
            record["status"] = "executed" if result.get("ok", False) else "failed"
            record["result"] = result
        except ServerAdminError as exc:
            record["status"] = "failed"
            record["result"] = {"ok": False, "code": exc.code, "message": str(exc)}
        record["resolved_ts"] = time.time()
        _save_pending(store)
        return dict(record)


def cancel_approval(approval_id: str) -> dict[str, Any]:
    with _lock:
        store = _load_pending()
        record = _get_pending_or_raise(approval_id)
        if record["status"] != "pending":
            raise ServerAdminError(
                f"批准請求狀態為 {record['status']}，不可取消",
                code="invalid_state",
                extra={"id": approval_id, "status": record["status"]},
            )
        record["status"] = "cancelled"
        record["resolved_ts"] = time.time()
        _save_pending(store)
        return dict(record)


# ── 工具執行（域層唯一入口）──


def execute_tool(name: str, params: dict[str, Any] | None = None, *, confirm: bool = False, role: str = "") -> dict[str, Any]:
    """執行具名工具；寫工具未確認時回傳 pending_confirmation 預覽（無副作用）。"""
    params = dict(params or {})
    if name not in sa.ALL_TOOLS:
        raise ServerAdminError(f"未知運維工具：{name}", code="unknown_tool", extra={"tool": name})
    result = sa.execute_named_tool(name, params, confirm=confirm, role=role)
    result.setdefault("tool", name)
    if role:
        result.setdefault("role", role)
    return result


def execute_for_agent(name: str, params: dict[str, Any] | None = None, *, role: str = "") -> dict[str, Any]:
    """公司運行時入口：寫工具未帶 confirmed 時自動轉人工批准隊列。"""
    params = dict(params or {})
    confirmed = bool(params.pop("confirmed", False) or params.pop("confirm", False))
    try:
        if name in sa.WRITE_TOOLS and not confirmed:
            preview = execute_tool(name, params, role=role)
            record = create_approval(name, params, preview, question=f"由公司角色 {role or 'agent'} 發起")
            return {
                "ok": True,
                "status": "pending_approval",
                "approval_id": record["id"],
                "message": preview.get("message", "已轉人工批准"),
                "tool": name,
            }
        return execute_tool(name, params, confirm=confirmed, role=role)
    except ServerAdminError as exc:
        return {"ok": False, "code": exc.code, "message": str(exc), "tool": name}


# ── 健康快照 / 巡檢 / 日報 ──


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


# ── LLM 規劃（ReAct 精簡版：單工具單輪，多輪由多次 ask 組成）──


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
    raw = call_llm(prompt, system=SA_SYSTEM_PROMPT, model=model)
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
    if _llm_ready():
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


# ── 公司 tool_registry 掛載 ──

_COMPANY_TOOL_NAMES: dict[str, str] = {
    "get_disk_usage": "server_disk_usage",
    "get_system_load": "server_system_load",
    "get_memory_usage": "server_memory_usage",
    "get_docker_status": "server_docker_status",
    "check_service": "server_service_status",
    "analyze_disk_growth": "server_disk_growth",
    "tail_log": "server_tail_log",
    "clean_old_packages": "server_clean_packages",
    "clean_temp_files": "server_clean_temp",
    "rotate_logs": "server_rotate_logs",
    "restart_service": "server_restart_service",
    "backup_incremental": "server_backup",
}
_WRITE_ROLES = ["manager", "devops", "sre", "server_admin"]


def register_company_tools(registry: Any) -> None:
    """向公司 tool_registry 註冊運維工具（讀開放、寫限維運角色且經批准隊列）。"""
    registry.register(
        name=_COMPANY_TOOL_NAMES["get_disk_usage"],
        description="磁盤使用率（存儲根或子目錄，只讀）",
        parameters={"target": {"type": "string", "description": "可選子目錄，如 packages"}},
        execute=lambda **kw: execute_for_agent("get_disk_usage", kw),
        readonly=True,
        timeout_seconds=30.0,
    )
    registry.register(
        name=_COMPANY_TOOL_NAMES["get_system_load"],
        description="CPU / 內存 / load average（只讀）",
        parameters={},
        execute=lambda **kw: execute_for_agent("get_system_load", kw),
        readonly=True,
        timeout_seconds=30.0,
    )
    registry.register(
        name=_COMPANY_TOOL_NAMES["get_memory_usage"],
        description="內存使用（只讀）",
        parameters={},
        execute=lambda **kw: execute_for_agent("get_memory_usage", kw),
        readonly=True,
        timeout_seconds=30.0,
    )
    registry.register(
        name=_COMPANY_TOOL_NAMES["get_docker_status"],
        description="所有 Docker 容器狀態（只讀）",
        parameters={},
        execute=lambda **kw: execute_for_agent("get_docker_status", kw),
        readonly=True,
        timeout_seconds=30.0,
    )
    registry.register(
        name=_COMPANY_TOOL_NAMES["check_service"],
        description="查詢 systemd 服務狀態（白名單內，只讀）",
        parameters={"name": {"type": "string", "description": "服務名，如 mysql"}},
        execute=lambda **kw: execute_for_agent("check_service", kw),
        readonly=True,
        timeout_seconds=30.0,
    )
    registry.register(
        name=_COMPANY_TOOL_NAMES["analyze_disk_growth"],
        description="磁盤增長分析：各目錄佔用與近 N 天增長來源（只讀）",
        parameters={
            "days": {"type": "integer", "description": "窗口天數（默認 7）"},
            "top": {"type": "integer", "description": "返回條數（默認 10）"},
        },
        execute=lambda **kw: execute_for_agent("analyze_disk_growth", kw),
        readonly=True,
        timeout_seconds=60.0,
    )
    registry.register(
        name=_COMPANY_TOOL_NAMES["tail_log"],
        description="讀取 logs/ 內日誌或審計日誌尾部（只讀）",
        parameters={
            "name": {"type": "string", "description": "日誌文件名或 audit"},
            "lines": {"type": "integer", "description": "行數（默認 100）"},
        },
        execute=lambda **kw: execute_for_agent("tail_log", kw),
        readonly=True,
        timeout_seconds=30.0,
    )
    registry.register(
        name=_COMPANY_TOOL_NAMES["clean_old_packages"],
        description="【寫·需批准】清理 packages/ 超過 N 天的 .zip",
        parameters={"days": {"type": "integer", "description": "天數（默認 7）"}, "confirmed": {"type": "boolean", "description": "已人工批准時為 true"}},
        execute=lambda **kw: execute_for_agent("clean_old_packages", kw),
        allowed_roles=list(_WRITE_ROLES),
        readonly=False,
        timeout_seconds=90.0,
    )
    registry.register(
        name=_COMPANY_TOOL_NAMES["clean_temp_files"],
        description="【寫·需批准】清理 temp/ 超過 N 天的文件",
        parameters={"days": {"type": "integer", "description": "天數（默認 3）"}, "confirmed": {"type": "boolean", "description": "已人工批准時為 true"}},
        execute=lambda **kw: execute_for_agent("clean_temp_files", kw),
        allowed_roles=list(_WRITE_ROLES),
        readonly=False,
        timeout_seconds=90.0,
    )
    registry.register(
        name=_COMPANY_TOOL_NAMES["rotate_logs"],
        description="【寫·需批准】gzip 輪轉 logs/ 超過 N MB 的 .log",
        parameters={"max_mb": {"type": "integer", "description": "MB 閾值（默認 100）"}, "confirmed": {"type": "boolean", "description": "已人工批准時為 true"}},
        execute=lambda **kw: execute_for_agent("rotate_logs", kw),
        allowed_roles=list(_WRITE_ROLES),
        readonly=False,
        timeout_seconds=90.0,
    )
    registry.register(
        name=_COMPANY_TOOL_NAMES["restart_service"],
        description="【寫·需批准】重啟白名單 systemd 服務",
        parameters={"name": {"type": "string", "description": "服務名（白名單內）"}, "confirmed": {"type": "boolean", "description": "已人工批准時為 true"}},
        execute=lambda **kw: execute_for_agent("restart_service", kw),
        allowed_roles=list(_WRITE_ROLES),
        readonly=False,
        timeout_seconds=90.0,
    )
    registry.register(
        name=_COMPANY_TOOL_NAMES["backup_incremental"],
        description="【寫·需批准】增量備份 assets/schematics 到備份目錄",
        parameters={"subdir": {"type": "string", "description": "子目錄（默認 assets）"}, "confirmed": {"type": "boolean", "description": "已人工批准時為 true"}},
        execute=lambda **kw: execute_for_agent("backup_incremental", kw),
        allowed_roles=list(_WRITE_ROLES),
        readonly=False,
        timeout_seconds=120.0,
    )
