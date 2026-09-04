"""控制面版聚合服務：GET /dashboard 的資料來源。

唯讀聚合五大區塊，供前端控制面版展示：
- stats        任務/存檔/記憶/OPC 的總覽統計
- tasks        任務摘要列表（created_at 降序）
- archives     對話存檔（AI 返回內容與生成內容，含引用記憶）
- opc_audit    OPC 操作審計（最近明細 + 匯總統計）
- capabilities Agent 能力與工具註冊表（MCP/Skills 等效面版）

所有檔案讀取皆 try/except 降級為空值，絕不拋錯；目錄可透過
環境變數覆蓋以利測試隔離：
- EVOL_ARCHIVE_DIR       對話存檔目錄
- OPC_AUDIT_LOG_DIR      OPC 審計日誌目錄
- EVOL_MEMORY_STORE_PATH 記憶庫 JSON 路徑
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from backend.company.roles import BUILTIN_TEMPLATES
from backend.core.llm_config import get_runtime_config
from backend.memory.json_store import JsonMemoryStore
from backend.services.archiver import DEFAULT_ARCHIVE_DIR
from backend.services.task_manager import task_manager

logger = logging.getLogger(__name__)

# repo 根目錄（backend/services/dashboard.py → 上兩層）
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AUDIT_DIR = REPO_ROOT / "opc_service" / "audit_logs"

MAX_ARCHIVE_FILES = 3
MAX_ARCHIVES = 20
MAX_AUDIT_RECENT = 20
# 最近 N 筆任務附帶完整 answer 與事件流（供控制台訊息串渲染）
MAX_FULL_TASKS = 8


def _archive_dir() -> Path:
    return Path(os.getenv("EVOL_ARCHIVE_DIR", str(DEFAULT_ARCHIVE_DIR)))


def _audit_dir() -> Path:
    return Path(os.getenv("OPC_AUDIT_LOG_DIR", str(DEFAULT_AUDIT_DIR)))


def _memory_store() -> JsonMemoryStore:
    path = os.getenv("EVOL_MEMORY_STORE_PATH")
    return JsonMemoryStore(path) if path else JsonMemoryStore()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """讀取 JSONL 檔案；損毀行跳過、檔案缺失回傳空列表。"""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    records: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            records.append(data)
    return records


def _sorted_jsonl(files: list[Path], limit: int) -> list[dict[str, Any]]:
    """合併多個 JSONL 檔案，依 timestamp 降序取前 limit 筆。"""
    records: list[dict[str, Any]] = []
    for f in files:
        records.extend(_read_jsonl(f))
    records.sort(key=lambda r: str(r.get("timestamp", "")), reverse=True)
    return records[:limit]


# ── 各區塊收集 ──


def _collect_tasks() -> list[dict[str, Any]]:
    records = sorted(
        task_manager.tasks.values(), key=lambda r: r.created_at, reverse=True
    )
    summaries = []
    for idx, record in enumerate(records):
        budget = record.budget if isinstance(record.budget, dict) else {}
        last_ts = record.events[-1]["ts"] if record.events else record.created_at
        entry: dict[str, Any] = {
            "task_id": record.task_id,
            "query": record.query,
            "strategy": record.strategy,
            "resolved_path": record.resolved_path,
            "status": record.status,
            "phase": record.phase,
            "score": record.score,
            "iteration": record.iteration,
            "spent": float(budget.get("task_spent") or 0),
            "created_at": record.created_at,
            "events_count": len(record.events),
            "answer_preview": (record.answer or "")[:300],
            "duration_sec": int(max(0, last_ts - record.created_at)),
        }
        # 最近幾筆任務附帶完整產出與事件流（控制台訊息串用）
        if idx < MAX_FULL_TASKS:
            entry["answer"] = record.answer or ""
            entry["events"] = record.events[-50:]
        summaries.append(entry)
    return summaries


def _collect_archives() -> list[dict[str, Any]]:
    directory = _archive_dir()
    try:
        files = sorted(directory.glob("evo_*.jsonl"), reverse=True)[:MAX_ARCHIVE_FILES]
    except OSError:
        return []
    return _sorted_jsonl(files, MAX_ARCHIVES)


def collect_opc_audit() -> dict[str, Any]:
    """公開：OPC 審計匯總（監控中心與控制面版共用）。"""
    return _collect_audit()


def _collect_audit() -> dict[str, Any]:
    directory = _audit_dir()
    try:
        files = sorted(directory.glob("opc_audit_*.jsonl"), reverse=True)
    except OSError:
        files = []
    all_records: list[dict[str, Any]] = []
    for f in files:
        all_records.extend(_read_jsonl(f))
    all_records.sort(key=lambda r: str(r.get("timestamp", "")), reverse=True)

    summary = {
        "total": len(all_records),
        "success": sum(1 for r in all_records if r.get("result") == "success"),
        "blocked": sum(1 for r in all_records if r.get("result") == "blocked"),
        "reads": sum(1 for r in all_records if r.get("operation") == "read"),
        "writes": sum(1 for r in all_records if r.get("operation") == "write"),
    }
    return {"recent": all_records[:MAX_AUDIT_RECENT], "summary": summary}


def _collect_capabilities(
    archives: list[dict[str, Any]],
    audit_summary: dict[str, Any],
    memories_count: int,
) -> list[dict[str, Any]]:
    cfg = get_runtime_config()
    company_count = sum(
        1 for t in task_manager.tasks.values() if t.resolved_path == "company"
    )
    roles = sorted({
        role.value
        for tpl in BUILTIN_TEMPLATES.values()
        for role in tpl.roles
    })
    referenced = sum(
        len(a.get("memory_items") or []) for a in archives
    )
    try:
        archive_files = len(list(_archive_dir().glob("evo_*.jsonl")))
    except OSError:
        archive_files = 0

    try:
        from backend.linkin.minecraft import monitor_status as minecraft_monitor_status

        mcp_status = minecraft_monitor_status()
    except Exception:  # noqa: BLE001
        mcp_status = {"dry_run": True, "connected": False, "world": "world"}

    return [
        {
            "key": "llm",
            "name": "LiteLLM 呼叫層",
            "icon": "🤖",
            "description": "統一 LLM 抽象層，所有節點經此呼叫模型，禁止直連供應商 SDK。",
            "status": "active" if cfg.get("api_key") else "idle",
            "stats": {
                "model": cfg.get("model", ""),
                "api_base": cfg.get("api_base", ""),
                "configured": bool(cfg.get("api_key")),
            },
        },
        {
            "key": "reflection_loop",
            "name": "反思閉環",
            "icon": "🔄",
            "description": "生成 → 評估 → 反思 → 改進迭代回路，確保交付品質達標。",
            "status": "active",
            "stats": {"usage": len(archives)},
        },
        {
            "key": "company_runtime",
            "name": "多代理人公司運行時",
            "icon": "🏢",
            "description": "Manager 分解 → 多角色並行執行 → Reviewer 審查 → Synthesizer 整合。",
            "status": "active" if company_count > 0 else "idle",
            "stats": {"usage": company_count, "roles": roles},
        },
        {
            "key": "memory",
            "name": "記憶檢索",
            "icon": "🧠",
            "description": "JSON / ChromaDB 向量記憶庫，供反思閉環檢索歷史經驗。",
            "status": "active" if memories_count > 0 else "idle",
            "stats": {"count": memories_count, "referenced": referenced},
        },
        {
            "key": "opc_ua",
            "name": "OPC UA 感知-診斷-行動",
            "icon": "🏭",
            "description": "工業數據讀寫與訂閱，寫操作經安全護欄（白名單/邊界/審計）。",
            "status": "active" if audit_summary.get("total", 0) > 0 else "idle",
            "stats": {
                "reads": audit_summary.get("reads", 0),
                "writes": audit_summary.get("writes", 0),
                "blocked": audit_summary.get("blocked", 0),
            },
        },
        {
            "key": "archiver",
            "name": "對話存檔服務",
            "icon": "🗄️",
            "description": "每次對話生命週期結構化存為 JSONL，供審計與行為分析。",
            "status": "active" if archive_files > 0 else "idle",
            "stats": {"files": archive_files},
        },
        {
            "key": "minecraft_mcp",
            "name": "Minecraft MCP",
            "icon": "▣",
            "description": "MineMCP JSON-RPC 橋接：公司角色可放置／破壞／填充方塊並執行指令。",
            "status": "active" if not mcp_status.get("dry_run") else "idle",
            "stats": {
                "dry_run": mcp_status.get("dry_run"),
                "connected": mcp_status.get("connected"),
                "world": mcp_status.get("world"),
            },
        },
    ]


# ── 主入口 ──


def collect_dashboard() -> dict[str, Any]:
    """聚合控制面版全部資料（唯讀、降級安全）。"""
    tasks = _collect_tasks()
    archives = _collect_archives()
    audit = _collect_audit()

    try:
        memories = _memory_store().all()
    except Exception:  # noqa: BLE001
        memories = []

    completed = [t for t in tasks if t["status"] == "completed"]
    failed = [t for t in tasks if t["status"] == "failed"]
    running = [t for t in tasks if t["status"] in ("running", "pending")]
    scored = [t["score"] for t in completed if isinstance(t["score"], (int, float))]

    stats = {
        "tasks_total": len(tasks),
        "tasks_completed": len(completed),
        "tasks_failed": len(failed),
        "tasks_running": len(running),
        "success_rate": round(len(completed) / len(tasks) * 100, 1) if tasks else 0,
        "avg_score": round(sum(scored) / len(scored), 2) if scored else None,
        "total_spent": round(
            sum(float(t.get("spent") or 0) for t in tasks), 4
        ),
        "total_iterations": sum(int(t.get("iteration") or 0) for t in tasks),
        "archives_count": len(archives),
        "memories_count": len(memories),
        "opc_total": audit["summary"]["total"],
        "opc_blocked": audit["summary"]["blocked"],
    }

    capabilities = _collect_capabilities(archives, audit["summary"], len(memories))

    return {
        "stats": stats,
        "tasks": tasks,
        "archives": archives,
        "opc_audit": audit,
        "capabilities": capabilities,
    }
