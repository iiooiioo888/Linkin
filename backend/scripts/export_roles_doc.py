"""匯出角色介紹：由 STANDARD_ROLES 產生 docs/company/roles.md。

用法：
    python -m backend.scripts.export_roles_doc
"""

from __future__ import annotations

from pathlib import Path

from backend.company.role_catalog import CATEGORY_LABELS, LEVEL_LABELS
from backend.company.roles import BUILTIN_TEMPLATES, STANDARD_ROLES
from backend.company.state import ROLE_CATEGORY_MAP

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "company" / "roles.md"


def main() -> None:
    lines: list[str] = []
    n = len(STANDARD_ROLES)
    nt = len(BUILTIN_TEMPLATES)

    lines += [
        "# 角色介紹",
        "",
        "> 來源：`backend/company/roles.py`（`STANDARD_ROLES`）＋"
        "`backend/linkin/roles.py`（靈境子角色種子）",
        f"> 對齊日期：2026-09-09 · 內建 **{n}** 席＋靈境 **16** 席＋模板 **{nt}**",
        "",
        "## 先分清楚三種「角色」",
        "",
        "| 種類 | 數量 | 程式來源 | 用途 |",
        "|------|------|----------|------|",
        f"| **公司 STANDARD_ROLES** | {n} | `backend/company/roles.py` | "
        "複雜任務／RAHO 調度的代理人席位 |",
        "| **靈境子角色** | 16 | `backend/linkin/roles.py` → `role_catalog` | "
        "建築／敘事／NPC／道具四部門 |",
        f"| **組織模板 BUILTIN_TEMPLATES** | {nt} | 同 `roles.py` | "
        "預組團隊（非獨立角色） |",
        "",
        "監控中心可覆寫 Prompt／預算／工具；持久化於 `EVOL_ROLE_CATALOG_PATH`"
        "（預設 `backend/data/role_catalog.json`）。",
        "詳見 [公司運行時](../architecture/company-runtime.md) · "
        "[術語表](../glossary.md)。",
        "",
        "## 組織職級 vs RAHO 指揮鏈",
        "",
        "兩套編號**不要混用**：",
        "",
        "| 維度 | 含義 |",
        "|------|------|",
        "| **組織職級 Level 0–4** | `RoleDefinition.level`："
        "數字越小越高層（Manager=0） |",
        "| **RAHO L5–L0** | 指揮／審查協議層："
        "用戶→審計→戰術→原子執行；獨立憲兵；環境核心注入 |",
        "",
        "```",
        "組織： L0 Manager → L1 Leads → L2 Domain Leads → L3 Executors → L4 Support",
        "RAHO： L5 用戶 → L4 需求審計 → L3 戰術指揮 → L2 原子執行",
        "       └─ 獨立 L1 憲兵（不隸屬 L3）",
        "       └─ L0 環境與記憶核心（滲透各層，不參與質詢）",
        "```",
        "",
    ]

    by_level: dict[int, list] = {}
    for rd in STANDARD_ROLES.values():
        by_level.setdefault(rd.level, []).append(rd)

    lines += [
        f"## 層級一覽（{n} 席）",
        "",
        "| 組織 Level | 名稱 | 席數 |",
        "|------------|------|------|",
    ]
    for lv in sorted(by_level):
        lines.append(
            f"| {lv} | {LEVEL_LABELS.get(lv, '?')} | {len(by_level[lv])} |"
        )
    lines.append("")

    raho = [
        ("requirement_auditor", "RAHO L4", "戰役／需求審計，語意鎖定與高層 DAG"),
        ("tactical_commander", "RAHO L3", "原子拆解、孵化 L2、Grill SOP"),
        ("atomic_executor", "RAHO L2", "專注單一 KPI，任務結束回收"),
        ("constitutional_inspector", "RAHO L1", "獨立四維驗收與簽核"),
        ("environment_kernel", "RAHO L0", "環境與記憶注入各層"),
    ]
    lines += [
        "## RAHO 脊柱（必讀）",
        "",
        "這五席是遞歸對抗分層的固定脊柱，與一般「部門員工」不同：",
        "",
        "| ID | 中文名 | RAHO | 一句話 |",
        "|----|--------|------|--------|",
    ]
    by_id = {rd.role_type.value: rd for rd in STANDARD_ROLES.values()}
    for rid, raho_l, blurb in raho:
        rd = by_id[rid]
        lines.append(f"| `{rid}` | {rd.name} | {raho_l} | {blurb} |")
    lines += [
        "",
        "完整協議見 "
        "[company-runtime.md](../architecture/company-runtime.md#raho遞歸對抗分層)。",
        "",
    ]

    for lv in sorted(by_level):
        items = sorted(by_level[lv], key=lambda x: x.role_type.value)
        lines += [
            f"## Level {lv}：{LEVEL_LABELS.get(lv, '?')}（{len(items)}）",
            "",
            "| ID | 名稱 | 分類 | 預算層 | 主要職責 |",
            "|----|------|------|--------|----------|",
        ]
        for rd in items:
            cat = ROLE_CATEGORY_MAP.get(rd.role_type)
            cat_l = CATEGORY_LABELS.get(cat.value, cat.value) if cat else "-"
            resp = "；".join(rd.responsibilities[:2]).replace("|", "/")
            if len(resp) > 120:
                resp = resp[:117] + "…"
            lines.append(
                f"| `{rd.role_type.value}` | {rd.name} | {cat_l} | "
                f"`{rd.default_tier.value}` | {resp} |"
            )
        lines.append("")

    desc_map = {
        "page_dev": "頁面／Mobile 前後端＋測試",
        "fullstack_app": "全端開發＋審查",
        "research_report": "研究調查與報告",
        "quick_task": "單一任務、成本最低",
        "full_company": "全席啟用",
        "quant_desk": "行情／回測／組合",
        "industrial_ops": "OPC／PLC／IoT",
        "story_studio": "敘事／世界觀／可調 MCP",
    }
    lines += [
        f"## 組織模板（{nt}）",
        "",
        "| 模板 ID | 名稱 | 適用 | 核心角色 |",
        "|--------|------|------|----------|",
    ]
    for tid, cfg in BUILTIN_TEMPLATES.items():
        role_ids = sorted(r.value for r in cfg.roles.keys())
        core = "、".join(f"`{x}`" for x in role_ids[:8])
        if len(role_ids) > 8:
            core += f" 等 {len(role_ids)} 席"
        lines.append(
            f"| `{tid}` | {cfg.name} | {desc_map.get(tid, '-')} | {core} |"
        )
    lines += [
        "",
        "> Minecraft 建造／靈境任務在預設 `quick_task` 時會改走 `story_studio`，"
        "以免只有 `developer` 卻無權放方塊。",
        "",
        "## 靈境子角色（16）",
        "",
        "由 `seed_linkin_roles()` 冪等寫入 `role_catalog`"
        "（ID 前綴 `custom_linkin_*`）。",
        "四部門 ×（總監＋執行者＋審查員＋記錄員）。",
        "",
        "| 部門 | 總監 ID | 執行者 | 審查員 | 記錄員 | 工具重點 |",
        "|------|---------|--------|--------|--------|----------|",
    ]
    depts = [
        ("build", "建築", "可 `place/fill/break`；總監另可 `execute_command`"),
        ("narrative", "敘事", "讀玩家狀態為主"),
        ("npc", "NPC", "讀玩家狀態為主"),
        ("item", "道具", "無 Minecraft 寫入工具"),
    ]
    for slug, title, tools in depts:
        lines.append(
            f"| {title} | `custom_linkin_{slug}_director` | "
            f"`…_{slug}_executor` | `…_{slug}_reviewer` | "
            f"`…_{slug}_scribe` | {tools} |"
        )
    lines += [
        "",
        "世界觀憲法為最高裁決；工具鐵律見 "
        "[Minecraft MCP](../linkin/minecraft-mcp.md) · "
        "[世界觀](../linkin/worldview.md)。",
        "",
        "## 開發者怎麼改角色",
        "",
        "| 需求 | 作法 |",
        "|------|------|",
        "| 改內建席 Prompt／職責 | 編輯 `backend/company/roles.py` "
        "對應 `ROLE_*`，補測試 |",
        "| 執行期覆寫／自定義席 | 監控中心或 `role_catalog` API；"
        "檔案 `backend/data/role_catalog.json` |",
        "| 新增組織模板 | 在 `roles.py` 加 `create_*` 並掛進 "
        "`BUILTIN_TEMPLATES` |",
        "| 靈境 16 席 | `backend/linkin/roles.py`＋`prompts.py`，"
        "啟動時冪等刷新 |",
        "| 禁止事項 | 勿讓角色直連 MineMCP／檔案系統工具；"
        "LLM 一律 `call_llm` |",
        "",
        "## 相關入口",
        "",
        "- [公司運行時](../architecture/company-runtime.md) · "
        "[目錄地圖](../structure.md) · [新人導覽](../onboarding.md)",
        "- 程式：`backend/company/roles.py` · `role_catalog.py` · "
        "`backend/linkin/roles.py`",
        "",
    ]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT} ({n} roles, {len(lines)} lines)")


if __name__ == "__main__":
    main()
