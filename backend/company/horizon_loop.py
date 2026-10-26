"""公開視域的任務級閉環。

自動完成：規劃固定主題 → 讀公開倉庫 → 自檢 → 失敗時改走備用來源 → 交出提案。
寫進系統前停下來等人點頭。權限、安全策略、核心目標、憲法、工具授權不能由這條閉環改。
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

ALLOWED_SURFACES = ("reference_note",)
FROZEN_SURFACES = (
    "permissions",
    "security_policy",
    "core_goals",
    "constitution",
    "tool_grants",
)
DOMAIN = "public_horizon"


def proposals_dir(root: Path) -> Path:
    return root / "proposals"


def accepted_path(root: Path) -> Path:
    return root / "accepted.json"


def classify_surface(kind: str) -> str:
    """回傳 ok、privilege。凍結面與未列出的能力都要人之外的系統自己停住。"""
    surface = (kind or "").strip()
    if surface in FROZEN_SURFACES or surface not in ALLOWED_SURFACES:
        return "privilege"
    return "ok"


def _hits(brief: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    rows: list[tuple[str, dict[str, Any]]] = []
    topics = brief.get("topics") if isinstance(brief.get("topics"), list) else []
    for topic in topics:
        if not isinstance(topic, dict):
            continue
        label = str(topic.get("label") or topic.get("id") or "主題")
        hits = topic.get("hits") if isinstance(topic.get("hits"), list) else []
        for hit in hits[:3]:
            if isinstance(hit, dict):
                rows.append((label, hit))
    return rows


def _note(brief: dict[str, Any]) -> str:
    lines = ["公開視域參考。只記錄倉庫名稱與網址。"]
    for label, hit in _hits(brief):
        name = str(hit.get("name") or "").strip()
        url = str(hit.get("url") or "").strip()
        lines.append(f"{label} {name} {url}".strip())
    return "\n".join(lines)[:2000]


def _metrics(brief: dict[str, Any], *, violations: int) -> dict[str, Any]:
    topics = brief.get("topics") if isinstance(brief.get("topics"), list) else []
    total = len(topics) or 1
    ok = sum(1 for topic in topics if isinstance(topic, dict) and topic.get("status") == "ok")
    return {
        "task_success": 1.0 if brief.get("ok") else 0.0,
        "automation_rate": 1.0 if brief.get("ok") else 0.0,
        "tool_accuracy": round(ok / total, 3),
        "safety_violations": violations,
        "cost_calls": len(topics),
        "rollback": True,
        "satisfaction": None,
    }


def _save(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_proposal(root: Path, proposal_id: str) -> dict[str, Any] | None:
    path = proposals_dir(root) / f"{proposal_id}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def attach_proposal(brief: dict[str, Any], root: Path, *, kind: str = "reference_note") -> dict[str, Any]:
    """把這次搜尋收成待確認提案。搜尋本身已結束，寫入參考筆記還沒發生。"""
    verdict = classify_surface(kind)
    retries = 1 if any(
        isinstance(topic, dict) and topic.get("source") == "github-api"
        for topic in (brief.get("topics") or [])
    ) else 0
    if verdict == "privilege":
        status = "stopped"
        reason = "privilege"
        detail = "這項會碰到凍結面，閉環停住，不寫入。"
        violations = 1
    elif not brief.get("ok"):
        status = "stopped"
        reason = "retry_limit"
        detail = "公開搜尋與備用來源都沒有結果，停止再試。"
        violations = 0
    else:
        status = "awaiting_confirmation"
        reason = "completed"
        detail = "搜尋完成。寫入參考筆記要點頭。"
        violations = 0
    proposal_id = "hz_" + uuid.uuid4().hex[:8]
    steps = ["plan", "execute", "check"]
    if retries:
        steps.append("retry")
    steps.append("deliver")
    if status == "awaiting_confirmation":
        steps.append("await_confirm")
    proposal = {
        "id": proposal_id,
        "domain": DOMAIN,
        "status": status,
        "allowed": list(ALLOWED_SURFACES),
        "frozen": list(FROZEN_SURFACES),
        "change": {"kind": kind, "text": _note(brief) if verdict == "ok" else ""},
        "loop": steps,
        "budget": {"max_topics": 3, "max_retries": 1, "retries_used": retries},
        "stop": {"reason": reason, "detail": detail},
        "metrics": _metrics(brief, violations=violations),
    }
    _save(proposals_dir(root) / f"{proposal_id}.json", proposal)
    brief["proposal_id"] = proposal_id
    brief["proposal"] = proposal
    return brief


def decide_proposal(root: Path, proposal_id: str, action: str, note: str = "") -> tuple[bool, str]:
    proposal = load_proposal(root, proposal_id)
    if proposal is None:
        return False, "找不到提案"
    if proposal.get("status") != "awaiting_confirmation":
        return False, "這份提案不在待確認"
    kind = str((proposal.get("change") or {}).get("kind") or "")
    if classify_surface(kind) == "privilege":
        proposal["status"] = "stopped"
        proposal["stop"] = {"reason": "privilege", "detail": "凍結面不能點頭通過。"}
        proposal["metrics"]["safety_violations"] = 1
        _save(proposals_dir(root) / f"{proposal_id}.json", proposal)
        return False, "越權，不會寫入"
    if action == "reject":
        proposal["status"] = "rejected"
        proposal["stop"] = {"reason": "cancelled", "detail": note or "已拒絕，不會寫入"}
        _save(proposals_dir(root) / f"{proposal_id}.json", proposal)
        return True, "已拒絕，不會寫入"
    if action != "approve":
        return False, "只能點頭或拒絕"
    text = str((proposal.get("change") or {}).get("text") or "").strip()
    if not text:
        return False, "沒有可寫入的參考筆記"
    proposal["status"] = "accepted"
    proposal["stop"] = {"reason": "completed", "detail": note or "已寫入參考筆記"}
    _save(proposals_dir(root) / f"{proposal_id}.json", proposal)
    _save(
        accepted_path(root),
        {"proposal_id": proposal_id, "text": text, "note": note},
    )
    return True, "已寫入參考筆記。權限、安全策略與核心目標維持不動"


def rollback_proposal(root: Path, proposal_id: str) -> tuple[bool, str]:
    proposal = load_proposal(root, proposal_id)
    if proposal is None:
        return False, "找不到提案"
    if proposal.get("status") != "accepted":
        return False, "只有已寫入的參考筆記可以撤銷"
    current = accepted_path(root)
    try:
        data = json.loads(current.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = None
    if isinstance(data, dict) and data.get("proposal_id") == proposal_id:
        current.unlink(missing_ok=True)
    proposal["status"] = "rolled_back"
    proposal["stop"] = {"reason": "completed", "detail": "已撤銷參考筆記"}
    _save(proposals_dir(root) / f"{proposal_id}.json", proposal)
    return True, "已撤銷參考筆記"


def accepted_note(root: Path | None = None) -> str:
    from backend.company.horizon import horizon_path

    target = accepted_path(root or horizon_path().parent)
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(data, dict):
        return ""
    return str(data.get("text") or "").strip()
