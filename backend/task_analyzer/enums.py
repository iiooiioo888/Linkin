"""任務分析器 v0.1 枚舉字典。

名稱與取值只增不刪、不可改名。每個取值都有繁中顯示名。
這裡只提供字典，不判斷規則、不轉移狀態、不檢查權限。
"""

from __future__ import annotations

from types import MappingProxyType

# 規格點名的枚舉。鍵名是契約，不可改。
PRIMARY_ENUM_NAMES: tuple[str, ...] = (
    "deployment",
    "task_type",
    "persistence",
    "criterion.metric",
    "hard_or_soft",
    "gap.severity",
    "question.category",
    "redline.category",
    "feasibility",
    "next_action",
    "input_channel",
    "priority",
)

# 實體要封閉欄位時使用的伴隨枚舉。同樣只增不刪。
COMPANION_ENUM_NAMES: tuple[str, ...] = (
    "gap.disposition",
    "rule.status",
    "resource.kind",
    "hardware.kind",
    "execution_path",
    "decision_source",
)

_ENUMS: dict[str, dict[str, str]] = {
    "deployment": {
        "cloud": "雲端",
        "local": "本地",
        "edge": "邊緣",
        "hybrid": "混合",
        "unspecified": "未指定",
    },
    "task_type": {
        "answer": "問答",
        "deliver": "交付",
        "operate": "運維",
        "research": "研究",
    },
    "persistence": {
        "none": "不保存",
        "session": "會話",
        "durable": "耐久",
        "audit_only": "僅審計",
    },
    "criterion.metric": {
        "pass_fail": "通過與否",
        "threshold": "門檻",
        "range": "區間",
        "latency": "延遲",
        "coverage": "覆蓋率",
        "cost": "成本",
        "quality_score": "品質分數",
    },
    "hard_or_soft": {
        "hard": "硬性",
        "soft": "軟性",
    },
    "gap.severity": {
        "blocking": "阻塞",
        "major": "重大",
        "minor": "次要",
        "info": "資訊",
    },
    "question.category": {
        "goal": "目標",
        "criterion": "衡量指標",
        "boundary": "邊界",
        "environment": "環境",
        "permission": "權限",
        "resource": "資源",
        "compliance": "合規",
        "budget": "預算",
    },
    "redline.category": {
        "safety": "安全",
        "privacy": "隱私",
        "compliance": "合規",
        "performance": "性能",
        "experience": "體驗",
        "ethics": "倫理",
    },
    "feasibility": {
        "go": "放行",
        "conditional_go": "有條件放行",
        "no_go": "不放行",
        "human_review": "轉人工",
        "pending": "未決",
    },
    "next_action": {
        "ask_user": "反問使用者",
        "re_discover": "重新盤點",
        "check_constraints": "底線校驗",
        "estimate_budget": "估算預算",
        "narrow_scope": "縮範圍",
        "handoff": "交給編排",
        "stop": "停止",
        "human_review": "轉人工",
    },
    "input_channel": {
        "chat": "對話",
        "task_api": "任務 API",
        "mcp": "MCP 介面",
        "company_console": "公司控制台",
        "system": "系統",
    },
    "priority": {
        "P0": "緊急",
        "P1": "高",
        "P2": "一般",
        "P3": "低",
    },
    "gap.disposition": {
        "present": "已有",
        "adapt": "需適配",
        "procure": "需採購",
        "missing": "缺失",
    },
    "rule.status": {
        "pass": "通過",
        "fail": "未通過",
        "unknown": "未知",
    },
    "resource.kind": {
        "mcp_server": "MCP 伺服器",
        "api": "應用程式介面",
        "dataset": "資料集",
        "file": "檔案",
        "skill": "技能",
        "opc_node": "OPC 節點",
    },
    "hardware.kind": {
        "cpu": "中央處理器",
        "gpu": "圖形處理器",
        "edge_box": "邊緣裝置",
        "unspecified": "未指定",
    },
    "execution_path": {
        "simple": "簡單路徑",
        "company": "公司路徑",
    },
    "decision_source": {
        "user_explicit": "本次指定",
        "user_default": "默認路徑",
        "admin_lock": "管理員鎖定",
        "fallback": "兜底",
    },
}

ENUMS: MappingProxyType[str, MappingProxyType[str, str]] = MappingProxyType(
    {name: MappingProxyType(values) for name, values in _ENUMS.items()}
)


def enum_values(name: str) -> tuple[str, ...]:
    """回傳枚舉取值，順序與字典相同。"""
    return tuple(ENUMS[name])


def display_name(name: str, value: str) -> str:
    """回傳繁中顯示名。名稱或取值不存在時拋 KeyError。"""
    return ENUMS[name][value]
