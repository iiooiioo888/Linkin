"""內建角色快照與內建角色目錄資料（_role_presets）（自 backend.company.role_catalog 抽出）。"""

from __future__ import annotations

from typing import Any

from backend.company.raho.protocol import attach_raho_fields
from backend.company.roles import BUILTIN_TEMPLATES, STANDARD_ROLES
from backend.company.state import ROLE_CATEGORY_MAP, ROLE_LEVEL, RoleType

from .constants import LEVEL_LABELS
from .normalize import _runtime_defaults


def _templates_for(role_id: str) -> list[str]:
    names: list[str] = []
    try:
        role = RoleType(role_id)
    except ValueError:
        return names
    for key, cfg in BUILTIN_TEMPLATES.items():
        if role in cfg.roles:
            names.append(key)
    return names


def _builtin_snapshot(role: RoleType) -> dict[str, Any]:
    definition = STANDARD_ROLES[role]
    level = definition.level if definition.level is not None else ROLE_LEVEL.get(role, 3)
    category = ROLE_CATEGORY_MAP.get(role)
    return attach_raho_fields(
        {
            "id": role.value,
            "name": definition.name,
            "level": level,
            "level_label": LEVEL_LABELS.get(level, "執行層"),
            "category": category.value if category else "management",
            "reporting_to": definition.reporting_to.value if definition.reporting_to else None,
            "can_delegate_to": [r.value for r in definition.can_delegate_to],
            "responsibilities": list(definition.responsibilities),
            "system_prompt": definition.system_prompt or "",
            "max_parallel_work": int(definition.max_parallel_work),
            "default_tier": definition.default_tier.value if definition.default_tier else "routine",
            **_runtime_defaults(),
            "is_custom": False,
            "is_builtin": True,
            "templates": _templates_for(role.value),
        }
    )


def _role_presets() -> list[dict[str, Any]]:
    """自定義角色快速模板：複製內建領域角色或建立額外實例。"""
    presets: list[dict[str, Any]] = []
    for role in (
        RoleType.QUANT_ANALYST,
        RoleType.CRAWLER,
        RoleType.OPC_ENGINEER,
        RoleType.STORY_WRITER,
        RoleType.UX_RESEARCHER,
        RoleType.PERF_ENG,
        RoleType.TRANSLATOR,
        RoleType.SUPPORT,
        RoleType.PROMPT_ENGINEER,
        RoleType.LEGAL,
        RoleType.GITHUB_OPS,
        RoleType.HUB_OPERATOR,
        RoleType.MEMORY_CURATOR,
        RoleType.RISK_ANALYST,
        RoleType.API_ENGINEER,
        RoleType.ML_ENGINEER,
        RoleType.RAG_ENGINEER,
        RoleType.EVAL_ENGINEER,
        RoleType.QA_AUTOMATION,
        RoleType.PEN_TESTER,
        RoleType.PLC_ENGINEER,
        RoleType.PORTFOLIO_MGR,
        RoleType.ROUTER_ENG,
        RoleType.CUSTOMER_SUCCESS,
    ):
        snap = _builtin_snapshot(role)
        presets.append(
            {
                "id": snap["id"],
                "name": snap["name"],
                "level": snap["level"],
                "category": snap["category"],
                "reporting_to": snap["reporting_to"],
                "system_prompt": snap["system_prompt"],
                "responsibilities": snap["responsibilities"],
                "default_tier": snap["default_tier"],
                "hint": "複製此內建角色為自定義實例（可改名、獨立預算）",
            }
        )
    extras = [
        {
            "id": "night_trader",
            "name": "夜盤交易員",
            "level": 3,
            "category": "finance",
            "reporting_to": "finance_lead",
            "system_prompt": "你是夜盤交易員，追蹤美股／期貨盤後行情，標明時區、缺口風險與倉位上限。",
            "responsibilities": ["盤後行情摘要", "缺口與隔夜風險", "標明倉位上限"],
            "default_tier": "reasoning",
            "hint": "StocksX 夜盤額外席位",
        },
        {
            "id": "news_crawler",
            "name": "新聞爬蟲",
            "level": 3,
            "category": "crawler",
            "reporting_to": "data_lead",
            "system_prompt": "你是新聞爬蟲專員，採集公告與新聞標題，去重並標明來源與時間。",
            "responsibilities": ["公告／新聞採集", "去重與來源追溯", "輸出結構化摘要"],
            "default_tier": "routine",
            "hint": "LittleCrawler 新聞線",
        },
        {
            "id": "line_operator",
            "name": "產線值班",
            "level": 3,
            "category": "industrial",
            "reporting_to": "industrial_lead",
            "system_prompt": "你是產線值班員，監控 OPC 告警並依 runbook 升級，禁止未授權寫入。",
            "responsibilities": ["告警值班", "runbook 升級", "交接紀錄"],
            "default_tier": "routine",
            "hint": "PysdnOPC 值班席",
        },
        {
            "id": "visual_novel",
            "name": "視覺小說編劇",
            "level": 3,
            "category": "creative",
            "reporting_to": "creative_lead",
            "system_prompt": "你是視覺小說編劇，產出分支選項、立繪提示與章節節奏。",
            "responsibilities": ["分支對白", "立繪／場景提示", "章節節奏"],
            "default_tier": "reasoning",
            "hint": "StoryForge 分支敘事",
        },
        {
            "id": "release_watcher",
            "name": "發布看守",
            "level": 3,
            "category": "platform",
            "reporting_to": "platform_lead",
            "system_prompt": "你看守 GitHub 發布與 CI 檢查，標明失敗步驟與回滾點。",
            "responsibilities": ["CI 失敗摘要", "發布清單", "回滾建議"],
            "default_tier": "routine",
            "hint": "自定義發布席",
        },
        {
            "id": "hub_budget_guard",
            "name": "Hub 預算守衛",
            "level": 3,
            "category": "hub",
            "reporting_to": "platform_lead",
            "system_prompt": "你在每次推理前檢查日預算與熔斷，超支則建議降級模型。",
            "responsibilities": ["預算攔截", "熔斷狀態", "降級建議"],
            "default_tier": "routine",
            "hint": "自定義 Hub 監控席",
        },
        {
            "id": "memory_janitor",
            "name": "記憶清理員",
            "level": 4,
            "category": "memory",
            "reporting_to": "tech_lead",
            "system_prompt": "你清理重複與過期向量記憶，並標明敏感內容不得寫入。",
            "responsibilities": ["去重", "過期策略", "敏感過濾"],
            "default_tier": "summary",
            "hint": "自定義記憶庫席",
        },
        {
            "id": "desk_night_risk",
            "name": "夜盤風控",
            "level": 3,
            "category": "finance",
            "reporting_to": "finance_lead",
            "system_prompt": "你是夜盤風控，檢查隔夜敞口、缺口與強制減倉條件。",
            "responsibilities": ["隔夜敞口", "缺口檢查", "減倉條件"],
            "default_tier": "reasoning",
            "hint": "量化桌夜盤風控席",
        },
        {
            "id": "opc_historian",
            "name": "製程歷史員",
            "level": 3,
            "category": "industrial",
            "reporting_to": "industrial_lead",
            "system_prompt": "你整理 OPC 歷史曲線與越界事件，標明時間窗與品質碼。",
            "responsibilities": ["歷史曲線", "越界事件", "品質碼"],
            "default_tier": "routine",
            "hint": "PysdnOPC 歷史席",
        },
        {
            "id": "rag_librarian",
            "name": "RAG 館員",
            "level": 3,
            "category": "ai",
            "reporting_to": "ai_lead",
            "system_prompt": "你維護切片、引用與未命中降級，禁止把機密寫進索引。",
            "responsibilities": ["切片品質", "引用檢查", "未命中降級"],
            "default_tier": "reasoning",
            "hint": "自定義 RAG 席",
        },
        {
            "id": "growth_onboard",
            "name": "啟用教練",
            "level": 3,
            "category": "growth",
            "reporting_to": "growth_lead",
            "system_prompt": "你設計新用戶啟用路徑與卡點，把流失轉成可指派缺陷。",
            "responsibilities": ["啟用路徑", "卡點分析", "流失轉缺陷"],
            "default_tier": "routine",
            "hint": "成長漏斗席",
        },
        {
            "id": "server_admin",
            "name": "服務器運維",
            "level": 4,
            "category": "devops",
            "reporting_to": "tech_lead",
            "system_prompt": (
                "你是 Linux 服務器運維智能體（AIOps），只能透過具名運維工具診斷與修復，"
                "絕不執行自由 shell。破壞性操作必須走人工批准隊列。"
            ),
            "responsibilities": ["巡檢與健康快照", "磁盤／日誌清理提案", "服務重啟批准"],
            "default_tier": "routine",
            "preferred_model": "qwen-max",
            "temperature": 0.2,
            "tools_allowed": [
                "server_disk_usage",
                "server_system_load",
                "server_memory_usage",
                "server_docker_status",
                "server_service_status",
                "server_disk_growth",
                "server_tail_log",
                "server_clean_packages",
                "server_clean_temp",
                "server_rotate_logs",
                "server_restart_service",
                "server_backup",
            ],
            "hint": "server_admin AIOps 席（寫操作需批准）",
        },
    ]
    presets.extend(extras)
    return presets
