"""將 `.agents/skills/` 內嵌 Agent 技能包同步進 Linkin 運行時技能庫與 MCP 註冊表。

來源：
- 技能目錄：`.agents/skills/<id>/SKILL.md`
- 上游鎖定：`skills-lock.json`（source、computedHash）
- MCP 範本：`backend/data/agent_mcp_manifest.json`

同步策略（upsert by id）：
- 不刪除、不覆蓋使用者自訂（managed=False）技能
- managed 技能依 lock hash 更新內容，保留 enabled / roles
- 新匯入技能預設 **停用**（避免 100+ 條同時注入提示詞）
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.company.mcp_clients import McpRegistry, mcp_registry
from backend.company.skills import SkillsStore, skills_store

logger = logging.getLogger(__name__)

AGENTS_SKILLS_DIR = Path(".agents/skills")
SKILLS_LOCK_PATH = Path("skills-lock.json")
MCP_MANIFEST_PATH = Path("backend/data/agent_mcp_manifest.json")

_CLI_STUB_IDS = frozenset({"agent-browser", "just-scrape"})
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_FM_LINE_RE = re.compile(r"^([a-zA-Z0-9_-]+):\s*(.*)$")


@dataclass
class SyncReport:
    skills_created: int = 0
    skills_updated: int = 0
    skills_unchanged: int = 0
    skills_skipped: int = 0
    mcp_created: int = 0
    mcp_updated: int = 0
    mcp_unchanged: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "skills": {
                "created": self.skills_created,
                "updated": self.skills_updated,
                "unchanged": self.skills_unchanged,
                "skipped": self.skills_skipped,
                "total_catalog": self.skills_created + self.skills_updated + self.skills_unchanged + self.skills_skipped,
            },
            "mcp": {
                "created": self.mcp_created,
                "updated": self.mcp_updated,
                "unchanged": self.mcp_unchanged,
            },
        }


def _strip_quotes(value: str) -> str:
    value = (value or "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def parse_skill_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """解析 SKILL.md YAML frontmatter（無 PyYAML 依賴的簡化版）。"""
    match = _FRONTMATTER_RE.match(text or "")
    if not match:
        return {}, (text or "").strip()
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        m = _FM_LINE_RE.match(line.strip())
        if not m:
            continue
        meta[m.group(1)] = _strip_quotes(m.group(2))
    body = (text or "")[match.end():].strip()
    return meta, body


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in ("true", "yes", "1")


def classify_skill_type(skill_id: str, meta: dict[str, str]) -> str:
    """cursor-only / cli-stub / agent-pack。"""
    if _truthy(meta.get("disable-model-invocation")) or _truthy(meta.get("hidden")):
        return "cursor-only"
    if skill_id in _CLI_STUB_IDS:
        return "cli-stub"
    compat = (meta.get("compatibility") or "").lower()
    if "cli" in compat or "just-scrape" in compat or "agent-browser" in compat:
        return "cli-stub"
    allowed = (meta.get("allowed-tools") or "").lower()
    if "agent-browser" in allowed or "just-scrape" in allowed:
        return "cli-stub"
    return "agent-pack"


def _load_skills_lock(path: Path = SKILLS_LOCK_PATH) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("skills-lock.json 讀取失敗：%s", exc)
        return {}
    skills = raw.get("skills") if isinstance(raw, dict) else None
    return skills if isinstance(skills, dict) else {}


def discover_agent_skill_dirs(root: Path = AGENTS_SKILLS_DIR) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir() and (p / "SKILL.md").is_file())


def build_skill_record(
    skill_dir: Path,
    lock: dict[str, dict[str, Any]],
    *,
    root: Path = AGENTS_SKILLS_DIR,
) -> dict[str, Any] | None:
    skill_id = skill_dir.name
    skill_md = skill_dir / "SKILL.md"
    try:
        raw = skill_md.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("無法讀取 %s：%s", skill_md, exc)
        return None
    meta, body = parse_skill_frontmatter(raw)
    if not body:
        return None
    lock_row = lock.get(skill_id) or {}
    name = (meta.get("name") or skill_id).strip()
    description = (meta.get("description") or "").strip()
    trigger = description[:500] if description else ""
    source = str(lock_row.get("source") or "").strip()
    content_hash = str(lock_row.get("computedHash") or "").strip()
    skill_type = classify_skill_type(skill_id, meta)
    rel_path = str(skill_md.relative_to(root.parent)) if skill_md.is_relative_to(root.parent) else str(skill_md)
    # 全文明為注入內容；frontmatter 摘要已映射到 description/trigger
    content = body
    if skill_type == "cursor-only":
        content = (
            "【Linkin 提示】此技能為 Cursor/Agent CLI 專用工作流（disable-model-invocation 或 hidden）。"
            " 以下內容可作參考閱讀，部分步驟需在 Cursor 或對應 CLI 中執行。\n\n"
            + content
        )
    elif skill_type == "cli-stub":
        content = (
            "【Linkin 提示】此技能依賴外部 CLI（如 just-scrape、agent-browser），非 MCP。"
            " Linkin 可注入方法論；實際抓取/瀏覽器操作需在已安裝 CLI 的環境執行。\n\n"
            + content
        )
    budget = min(20000, max(2400, len(content) // 2))
    return {
        "skill_id": skill_id,
        "name": name,
        "content": content,
        "description": description,
        "trigger": trigger,
        "source": source,
        "skill_type": skill_type,
        "source_path": rel_path,
        "content_hash": content_hash,
        "skill_budget": budget,
    }


def sync_agent_skills(
    store: SkillsStore | None = None,
    registry: McpRegistry | None = None,
    *,
    skills_root: Path = AGENTS_SKILLS_DIR,
    lock_path: Path = SKILLS_LOCK_PATH,
    mcp_manifest_path: Path = MCP_MANIFEST_PATH,
    sync_mcp: bool = True,
) -> SyncReport:
    """掃描 .agents/skills 並 upsert 至 skills.json / mcp_servers.json。"""
    store = store or skills_store
    registry = registry or mcp_registry
    report = SyncReport()
    lock = _load_skills_lock(lock_path)

    for skill_dir in discover_agent_skill_dirs(skills_root):
        row = build_skill_record(skill_dir, lock, root=skills_root)
        if not row:
            report.skills_skipped += 1
            continue
        try:
            _, action = store.sync_managed(
                skill_id=row["skill_id"],
                name=row["name"],
                content=row["content"],
                description=row["description"],
                trigger=row["trigger"],
                source=row["source"],
                skill_type=row["skill_type"],
                source_path=row["source_path"],
                content_hash=row["content_hash"],
                default_enabled=False,
                skill_budget=row["skill_budget"],
            )
        except ValueError as exc:
            logger.warning("同步技能 %s 失敗：%s", row["skill_id"], exc)
            report.skills_skipped += 1
            continue
        if action == "created":
            report.skills_created += 1
        elif action == "updated":
            report.skills_updated += 1
        elif action == "unchanged":
            report.skills_unchanged += 1
        else:
            report.skills_skipped += 1

    if sync_mcp:
        _sync_mcp_manifest(registry, mcp_manifest_path, report)

    logger.info(
        "Agent 技能同步完成：skills +%d ~%d =%d skip %d | mcp +%d ~%d =%d",
        report.skills_created,
        report.skills_updated,
        report.skills_unchanged,
        report.skills_skipped,
        report.mcp_created,
        report.mcp_updated,
        report.mcp_unchanged,
    )
    return report


def _sync_mcp_manifest(registry: McpRegistry, path: Path, report: SyncReport) -> None:
    if not path.exists():
        return
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("MCP manifest 讀取失敗：%s", exc)
        return
    for row in raw.get("servers", []) if isinstance(raw, dict) else []:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("id") or "").strip()
        if not sid:
            continue
        try:
            _, action = registry.sync_managed(
                server_id=sid,
                name=str(row.get("name") or sid),
                transport=str(row.get("transport") or "http"),
                command=str(row.get("command") or ""),
                env=dict(row.get("env") or {}),
                url=str(row.get("url") or ""),
                headers=dict(row.get("headers") or {}),
                enabled=bool(row.get("enabled", False)),
                allowed_tools=row.get("allowed_tools"),
                readonly=bool(row.get("readonly", True)),
                timeout=float(row.get("timeout", 20.0)),
                description=str(row.get("description") or ""),
            )
        except ValueError as exc:
            logger.warning("同步 MCP %s 失敗：%s", sid, exc)
            continue
        if action == "created":
            report.mcp_created += 1
        elif action == "updated":
            report.mcp_updated += 1
        else:
            report.mcp_unchanged += 1


def sync_on_boot() -> SyncReport | None:
    """啟動時同步；LINKIN_SYNC_AGENT_SKILLS=false 可關閉。"""
    flag = os.getenv("LINKIN_SYNC_AGENT_SKILLS", "true").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return None
    return sync_agent_skills()
