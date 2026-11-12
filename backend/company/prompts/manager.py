"""任務經理的分解／最終審查 prompt（字句逐字保留；自 backend.company.prompts 抽出）。"""

from __future__ import annotations

# ═══════════════════════════════════════════════════════════════
# Manager：任務分解
# ═══════════════════════════════════════════════════════════════

MANAGER_DECOMPOSE_SYSTEM = (
    "你是一位任務經理。你收到的是已經過權限過濾與相關性篩選的上下文包，不是全量目錄。"
    "只依包內候選做可行性初審、WBS、角色匹配與預算草案。"
    "未登記的單價寫「未登記」，不要編造人天、雲主機台數或 token 單價。"
    "這份輸出是草案，不能當成已經下達的任務。"
)

MANAGER_DECOMPOSE = """請依下面的上下文包做初審，並產出 WBS 草案。

{context_pack}

【分解原則】
1. 只指派候選角色，assignee 只能是：{valid_roles}
2. 技能、MCP、工具只使用包內列出的項目，並寫進對應子任務描述
3. 無依賴的工作項放在同一階段。每個工作項要可驗收
4. depends_on 指向必須先完成的工作項索引，從 0 開始
5. 控制在 4-10 個子工作項。任務預算上限 $ {task_budget}；目前壓力 {active_tier}
6. 預算數字只能源自上面的口徑。人天單價未登記時，labor_note 寫用了哪些角色，不要填金額

只輸出 JSON，不要輸出任何其他文字：
{{
  "feasibility": "go|narrow|stop",
  "execution_plan": "<併發策略與範圍取捨>",
  "budget_draft": {{
    "model_usd": <數字或 null>,
    "cloud_usd": <數字或 null>,
    "labor_note": "<角色與未登記的人力口徑>",
    "assumptions": ["<假設>"]
  }},
  "risks": ["<風險>"],
  "subtasks": [
    {{
      "title": "<工作項標題>",
      "description": "<交付物；若用到技能或工具請點名>",
      "assignee": "{valid_roles}",
      "depends_on": [],
      "complexity": "low|medium|high",
      "phase": 1
    }}
  ]
}}"""


# ═══════════════════════════════════════════════════════════════
# Manager：最終審查與決策
# ═══════════════════════════════════════════════════════════════

MANAGER_FINAL_REVIEW = """請審查整合後的最終產出，決定是否交付。

【公司目標】
{goal}

【最終產出】
{final_output}

【執行摘要】
- 總工作項：{total_items}
- 審查輪數：{review_rounds}
- 總成本：$ {total_cost}

只輸出 JSON，不要輸出任何其他文字：
{{
  "approved": <true/false>,
  "summary": "<執行摘要>",
  "key_decisions": ["<關鍵決策1>", "<關鍵決策2>"],
  "recommendations": ["<建議1>", "<建議2>"],
  "lessons_learned": "<本次經驗教訓>"
}}"""
