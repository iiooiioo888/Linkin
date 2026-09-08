"""任務拆分器 —— EvoLoop 核心主功能。

將複雜目標分解為可並行執行的子工作項，是整個公司運行時的
第一大階段。支援三種拆分策略：

  1. LLM 驅動：利用 LLM 理解目標語義，智能分解與角色指派
  2. 模板驅動：基於內建任務模板（如 page_dev）快速匹配
  3. 規則驅動：簡單關鍵字拆分，適用於低複雜度任務

設計原則：
  - 獨立模組：可脫離 CompanyOrchestrator 單獨使用與測試
  - 策略可插拔：三種策略可根據場景自動選擇或手動指定
  - 層級感知：充分利用 org_chart 規劃並行階段與依賴鏈
  - 預算感知：根據預算壓力自動選擇合適的拆分策略
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from backend.company.budget import BudgetManager, CostTracker
from backend.company.prompts import (
    PromptConfig,
)
from backend.company.state import (
    BudgetTier,
    CompanyConfig,
    RoleType,
    WorkItem,
    WorkItemStatus,
)
from backend.company.work_item import WorkItemManager
from backend.core.llm import call_llm, llm_kwargs_for_role, parse_json_response

logger = logging.getLogger(__name__)

# ── 拆分結果快取（優化 #13）──
_DECOMPOSE_CACHE_SIZE = int(os.getenv("EVOL_DECOMPOSE_CACHE_SIZE", "64")) if 'os' in dir() else 64
import hashlib
import os
from collections import OrderedDict as _OrderedDict

_decompose_cache: _OrderedDict[str, DecompositionResult] = _OrderedDict()


# ═══════════════════════════════════════════════════════════════
# 拆分策略
# ═══════════════════════════════════════════════════════════════

class DecompositionStrategy(str, Enum):
    """任務拆分策略。

    - LLM:      利用 LLM 理解目標語義，智能分解（最強大，有成本）
    - TEMPLATE: 基於內建任務模板匹配（快速，適合已知場景）
    - RULE:     簡單關鍵字/規則拆分（零成本，適合簡單任務）
    - AUTO:     自動選擇最優策略（預設）
    """
    LLM = "llm"
    TEMPLATE = "template"
    RULE = "rule"
    AUTO = "auto"


# ═══════════════════════════════════════════════════════════════
# 拆分結果
# ═══════════════════════════════════════════════════════════════

@dataclass
class DecompositionResult:
    """任務拆分結果：包含子工作項描述與執行計劃。"""

    goal: str
    strategy: DecompositionStrategy
    subtasks: list[dict[str, Any]] = field(default_factory=list)
    execution_plan: str = ""
    phases: list[list[int]] = field(default_factory=list)  # 每階段的工作項索引
    meta: dict[str, Any] = field(default_factory=dict)      # 額外元數據

    @property
    def subtask_count(self) -> int:
        return len(self.subtasks)

    @property
    def phase_count(self) -> int:
        return len(self.phases)

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "strategy": self.strategy.value,
            "subtask_count": self.subtask_count,
            "phase_count": self.phase_count,
            "execution_plan": self.execution_plan,
            "subtasks": self.subtasks,
            "phases": self.phases,
            "meta": self.meta,
        }


# ═══════════════════════════════════════════════════════════════
# 任務拆分器
# ═══════════════════════════════════════════════════════════════

class TaskDecomposer:
    """任務拆分器 —— 將複雜目標分解為可執行的子工作項。

    這是 EvoLoop 公司運行時的第一大階段，也是最重要的主功能模組。
    支援三種拆分策略，可根據場景自動選擇或手動指定。

    使用範例：
        >>> config = create_page_dev_team()
        >>> budget = BudgetManager(config.budget)
        >>> decomposer = TaskDecomposer(config, budget)
        >>> result = await decomposer.decompose("開發一個用戶登入頁面")
        >>> items = decomposer.build_work_items(result)
    """

    def __init__(
        self,
        config: CompanyConfig,
        budget_manager: BudgetManager,
        work_items: WorkItemManager | None = None,
        prompt_config: PromptConfig | None = None,
    ):
        self.config = config
        self.budget = budget_manager
        self.work_items = work_items or WorkItemManager()
        self.prompt_config = prompt_config or config.prompt_config

    # ═══════════════════════════════════════════════════════════
    # 公開 API
    # ═══════════════════════════════════════════════════════════

    async def decompose(
        self,
        goal: str,
        strategy: DecompositionStrategy = DecompositionStrategy.AUTO,
    ) -> DecompositionResult:
        """將目標分解為子工作項描述（優化 #13：拆分結果快取）。

        Args:
            goal: 要分解的目標描述
            strategy: 拆分策略（預設 AUTO，自動選擇最優策略）

        Returns:
            DecompositionResult: 包含子工作項描述、執行計劃、階段資訊
        """
        # 自動選擇策略
        if strategy == DecompositionStrategy.AUTO:
            strategy = self._select_strategy(goal)

        # 查詢快取（相同目標 + 策略 → 復用拆分結果）
        cache_key = hashlib.sha256(f"{strategy.value}:{goal}".encode()).hexdigest()[:24]
        if cache_key in _decompose_cache:
            logger.info("任務拆分快取命中：%s", cache_key[:12])
            _decompose_cache.move_to_end(cache_key)
            return _decompose_cache[cache_key]

        logger.info("任務拆分開始：goal=%s，strategy=%s", goal[:80], strategy.value)

        if strategy == DecompositionStrategy.TEMPLATE:
            result = self._template_decompose(goal)
        elif strategy == DecompositionStrategy.RULE:
            result = self._rule_decompose(goal)
        else:
            result = await self._llm_decompose(goal)

        # 存入快取
        _decompose_cache[cache_key] = result
        if len(_decompose_cache) > _DECOMPOSE_CACHE_SIZE:
            _decompose_cache.popitem(last=False)

        logger.info(
            "任務拆分完成：%d 個子工作項，%d 個階段",
            result.subtask_count,
            result.phase_count,
        )
        return result

    def build_work_items(
        self,
        result: DecompositionResult,
        created_by: RoleType = RoleType.MANAGER,
    ) -> list[WorkItem]:
        """將拆分結果轉換為實際工作項（含依賴解析）。

        這是 decompose 的後續步驟：將 LLM/模板產出的子工作項描述
        轉換為 WorkItemManager 中的實際工作項，並解析索引式依賴為實際 ID。

        Args:
            result: decompose() 的回傳結果
            created_by: 創建者角色

        Returns:
            list[WorkItem]: 已建立的工作項列表（狀態為 READY）
        """
        # 步驟 1：建立所有工作項（暫無依賴）
        created_items: list[WorkItem] = []
        id_map: dict[int, str] = {}

        for i, task in enumerate(result.subtasks):
            role_str = task.get("assignee", "developer")
            try:
                assignee = RoleType(role_str)
            except ValueError:
                assignee = RoleType.DEVELOPER

            complexity = task.get("complexity", "medium")
            tier_map = {
                "low": BudgetTier.SUMMARY,
                "medium": BudgetTier.ROUTINE,
                "high": BudgetTier.REASONING,
            }

            item = self.work_items.create(
                title=task["title"],
                description=task.get("description", ""),
                assignee=assignee,
                created_by=created_by,
                depends_on=[],  # 稍後設定
                tier=tier_map.get(complexity, BudgetTier.ROUTINE),
            )
            item.transition_to(WorkItemStatus.READY)
            created_items.append(item)
            id_map[i] = item.id

        # 步驟 2：設定依賴關係（索引 → 實際 ID）
        for i, task in enumerate(result.subtasks):
            dep_indices = task.get("depends_on", [])
            if isinstance(dep_indices, list) and dep_indices:
                item = created_items[i]
                item.depends_on = [
                    id_map[idx] for idx in dep_indices
                    if idx in id_map
                ]

        logger.info(
            "工作項建立完成：%d 個（含 %d 個有依賴）",
            len(created_items),
            sum(1 for item in created_items if item.depends_on),
        )
        return created_items

    def plan_parallel_execution(
        self,
        subtasks: list[dict[str, Any]],
    ) -> list[list[int]]:
        """根據依賴關係規劃並行執行階段。

        使用拓樸排序將子工作項分組為可並行執行的階段。

        Args:
            subtasks: 子工作項列表（含 depends_on 索引）

        Returns:
            list[list[int]]: 每個階段包含的工作項索引列表
        """
        n = len(subtasks)
        if n == 0:
            return []

        # 計算每個工作項的深度（最長依賴鏈長度）
        depth = [0] * n
        changed = True
        while changed:
            changed = False
            for i, task in enumerate(subtasks):
                deps = task.get("depends_on", [])
                if isinstance(deps, list):
                    for dep_idx in deps:
                        if isinstance(dep_idx, int) and 0 <= dep_idx < n:
                            new_depth = depth[dep_idx] + 1
                            if new_depth > depth[i]:
                                depth[i] = new_depth
                                changed = True

        # 按深度分組
        max_depth = max(depth) if depth else 0
        phases: list[list[int]] = [[] for _ in range(max_depth + 1)]
        for i, d in enumerate(depth):
            phases[d].append(i)

        # 移除空階段
        return [p for p in phases if p]

    # ═══════════════════════════════════════════════════════════
    # 策略選擇
    # ═══════════════════════════════════════════════════════════

    def _select_strategy(self, goal: str) -> DecompositionStrategy:
        """根據目標特徵與預算壓力自動選擇拆分策略。

        決策邏輯：
          1. 預算壓力 >= 90% → RULE（零成本）
          2. 目標匹配已知模板 → TEMPLATE（快速、低成本）
          3. 預設 → LLM（最強大）
        """
        # 預算壓力高時降級
        if self.budget.budget_pressure >= 0.9:
            logger.info("預算壓力 %.0f%%，使用 RULE 策略", self.budget.budget_pressure * 100)
            return DecompositionStrategy.RULE

        # 檢查是否匹配已知模板
        goal_lower = goal.lower()
        for keyword in self.prompt_config.template_keywords:
            if keyword in goal_lower:
                logger.info("目標匹配模板關鍵字 '%s'，使用 TEMPLATE 策略", keyword)
                return DecompositionStrategy.TEMPLATE

        # 預設使用 LLM
        return DecompositionStrategy.LLM

    # ═══════════════════════════════════════════════════════════
    # LLM 驅動拆分
    # ═══════════════════════════════════════════════════════════

    async def _llm_decompose(self, goal: str) -> DecompositionResult:
        """LLM 驅動拆分：利用 LLM 理解目標語義，智能分解。"""
        org_chart_str = self._format_org_chart()
        role_descriptions = self._format_role_descriptions()
        try:
            from backend.company.role_catalog import resolve_runtime
            valid_roles = "/".join(
                rt.value
                for rt in self.config.roles
                if resolve_runtime(rt.value).get("enabled", True)
            )
        except Exception:  # noqa: BLE001
            valid_roles = "/".join(rt.value for rt in self.config.roles)

        model = self.budget.resolve_model_for_tier(BudgetTier.REASONING)
        llm_opts: dict = {}
        try:
            from backend.company.role_catalog import resolve_runtime

            runtime = resolve_runtime(RoleType.MANAGER.value)
            if runtime.get("preferred_model"):
                model = runtime["preferred_model"]
            llm_opts = llm_kwargs_for_role(runtime)
        except Exception:  # noqa: BLE001
            llm_opts = {}
        prompt = self.prompt_config.manager_decompose.format(
            goal=goal,
            org_chart=org_chart_str,
            role_descriptions=role_descriptions,
            valid_roles=valid_roles,
            task_budget=self.config.budget.task_limit_usd,
            active_tier=self.budget.budget_pressure,
        )
        try:
            from backend.company.raho.scorecard import planning_paradigm_hint

            hint = planning_paradigm_hint()
            if hint:
                prompt = prompt + "\n\n" + hint
        except Exception:  # noqa: BLE001
            pass

        try:
            raw = call_llm(
                prompt,
                system=self.prompt_config.manager_decompose_system,
                model=model,
                **llm_opts,
            )
            cost = CostTracker.estimate_cost_rough(model, "high")
            self.budget.record_cost(cost)

            result = parse_json_response(raw)
            subtasks = result.get("subtasks", [])
            execution_plan = result.get("execution_plan", "")

            # 從 LLM 回傳的 phase 欄位提取階段資訊
            phases = self._extract_phases_from_subtasks(subtasks)

            return DecompositionResult(
                goal=goal,
                strategy=DecompositionStrategy.LLM,
                subtasks=subtasks,
                execution_plan=execution_plan,
                phases=phases,
                meta={"model": model, "cost": round(cost, 4)},
            )

        except Exception as exc:  # noqa: BLE001 - 降級兜底：LLM 失敗時改用 RULE 策略
            logger.error("LLM 拆分失敗，降級為 RULE 策略：%s", exc)
            return self._rule_decompose(goal)

    # ═══════════════════════════════════════════════════════════
    # 模板驅動拆分
    # ═══════════════════════════════════════════════════════════

    def _template_decompose(self, goal: str) -> DecompositionResult:
        """模板驅動拆分：基於內建任務模板匹配。

        根據目標關鍵字匹配最合適的模板，並自動調整角色以匹配
        當前團隊配置。
        """
        goal_lower = goal.lower()

        # 尋找最匹配的模板
        matched_template = None
        matched_keyword = ""
        for keyword, template in self.prompt_config.template_keywords.items():
            if keyword in goal_lower:
                matched_template = template
                matched_keyword = keyword
                break

        if matched_template is None:
            # 無匹配模板，降級為 RULE
            logger.info("無匹配模板，降級為 RULE 策略")
            return self._rule_decompose(goal)

        # 過濾：只保留團隊中存在的角色
        available_roles = set(rt.value for rt in self.config.roles)
        subtasks = []
        for task in matched_template:
            role = task.get("assignee", "")
            # 若角色不在團隊中，替換為最接近的可用角色
            if role and role not in available_roles:
                replacement = self._find_closest_role(role, available_roles)
                if replacement:
                    task = {**task, "assignee": replacement}
                else:
                    continue  # 無可用角色，跳過此工作項
            subtasks.append(task)

        phases = self.plan_parallel_execution(subtasks)

        return DecompositionResult(
            goal=goal,
            strategy=DecompositionStrategy.TEMPLATE,
            subtasks=subtasks,
            execution_plan=f"使用模板 '{matched_keyword}' 拆分，共 {len(subtasks)} 個子工作項",
            phases=phases,
            meta={"template": matched_keyword},
        )

    # ═══════════════════════════════════════════════════════════
    # 規則驅動拆分
    # ═══════════════════════════════════════════════════════════

    def _rule_decompose(self, goal: str) -> DecompositionResult:
        """規則驅動拆分：簡單關鍵字拆分，零 LLM 成本。

        適用於簡單任務或預算緊張時。根據目標長度與關鍵字
        產生 1-3 個基本工作項。
        """
        available_roles = set(rt.value for rt in self.config.roles)

        # 選擇最佳執行角色
        primary_role = self._pick_best_role(goal, available_roles)

        # 根據目標複雜度決定拆分數量
        word_count = len(goal)
        if word_count < 30:
            # 簡單任務：單一工作項
            subtasks = [{
                "title": goal,
                "description": f"執行目標：{goal}",
                "assignee": primary_role,
                "depends_on": [],
                "complexity": "low",
                "phase": 1,
            }]
        elif word_count < 100:
            # 中等任務：分析 + 執行
            subtasks = [
                {
                    "title": f"分析：{goal[:40]}",
                    "description": f"分析需求並規劃執行方案：{goal}",
                    "assignee": "analyst" if "analyst" in available_roles else primary_role,
                    "depends_on": [],
                    "complexity": "medium",
                    "phase": 1,
                },
                {
                    "title": f"執行：{goal[:40]}",
                    "description": f"根據分析結果執行：{goal}",
                    "assignee": primary_role,
                    "depends_on": [0],
                    "complexity": "medium",
                    "phase": 2,
                },
            ]
        else:
            # 複雜任務：分析 + 執行 + 審查
            reviewer_role = "reviewer" if "reviewer" in available_roles else primary_role
            subtasks = [
                {
                    "title": f"分析：{goal[:40]}",
                    "description": f"分析需求並規劃執行方案：{goal}",
                    "assignee": "analyst" if "analyst" in available_roles else primary_role,
                    "depends_on": [],
                    "complexity": "medium",
                    "phase": 1,
                },
                {
                    "title": f"執行：{goal[:40]}",
                    "description": f"根據分析結果執行：{goal}",
                    "assignee": primary_role,
                    "depends_on": [0],
                    "complexity": "high",
                    "phase": 2,
                },
                {
                    "title": f"審查：{goal[:40]}",
                    "description": f"審查交付物品質並提供回饋：{goal}",
                    "assignee": reviewer_role,
                    "depends_on": [1],
                    "complexity": "low",
                    "phase": 3,
                },
            ]

        phases = self.plan_parallel_execution(subtasks)

        return DecompositionResult(
            goal=goal,
            strategy=DecompositionStrategy.RULE,
            subtasks=subtasks,
            execution_plan=f"規則拆分：{len(subtasks)} 個子工作項，{len(phases)} 個階段",
            phases=phases,
            meta={"word_count": word_count},
        )

    # ═══════════════════════════════════════════════════════════
    # 輔助方法
    # ═══════════════════════════════════════════════════════════

    def _format_org_chart(self) -> str:
        """格式化組織架構樹（供 Prompt 使用）。"""
        if not self.config.org_chart:
            return "\n".join(
                f"- {rt.value}（{rd.name}）"
                for rt, rd in self.config.roles.items()
            )

        def _format_subtree(role: RoleType, indent: int = 0) -> list[str]:
            lines = []
            role_def = self.config.roles.get(role)
            name = role_def.name if role_def else role.value
            level = self.config.get_role_level(role)
            lines.append(f"{'  ' * indent}├─ {role.value}（{name}，Level {level}）")
            for sub in self.config.org_chart.get(role, []):
                lines.extend(_format_subtree(sub, indent + 1))
            return lines

        roots = [r for r in self.config.roles if self.config.get_role_level(r) == 0]
        if not roots and self.config.roles:
            roots = [next(iter(self.config.roles))]

        lines = ["組織層級結構："]
        for root in roots:
            lines.extend(_format_subtree(root))
        return "\n".join(lines)

    def _format_role_descriptions(self) -> str:
        """格式化角色能力說明（供 Prompt 使用）。"""
        lines = []
        for rt, rd in self.config.roles.items():
            resp = "、".join(rd.responsibilities[:3])
            lines.append(
                f"- {rt.value}（{rd.name}，Level {rd.level}）：{resp}"
            )
        return "\n".join(lines)

    def _extract_phases_from_subtasks(
        self,
        subtasks: list[dict[str, Any]],
    ) -> list[list[int]]:
        """從 subtasks 的 phase 欄位提取階段分組。

        優先使用 LLM 標註的 phase，若無則使用依賴拓樸計算。
        """
        # 檢查是否所有 subtask 都有 phase 欄位
        has_phases = all(
            isinstance(t.get("phase"), (int, float))
            for t in subtasks
        )
        if has_phases:
            max_phase = max(int(t.get("phase", 1)) for t in subtasks)
            phases: list[list[int]] = [[] for _ in range(max_phase)]
            for i, t in enumerate(subtasks):
                p = int(t.get("phase", 1)) - 1
                phases[p].append(i)
            return [p for p in phases if p]

        # 回退到依賴拓樸計算
        return self.plan_parallel_execution(subtasks)

    def _find_closest_role(
        self,
        target: str,
        available: set[str],
    ) -> str | None:
        """尋找最接近的可用角色。"""
        # 精確匹配
        if target in available:
            return target

        # 角色替換映射
        fallback_map: dict[str, str] = {
            "ui_designer": "developer",
            "css_dev": "developer",
            "js_dev": "developer",
            "backend_dev": "developer",
            "tester": "developer",
            "devops": "developer",
            "architect": "tech_lead",
            "frontend_lead": "tech_lead",
            "backend_lead": "tech_lead",
            "test_lead": "tech_lead",
            "tech_lead": "manager",
            "analyst": "developer",
            "reviewer": "developer",
            "synthesizer": "developer",
            "coordinator": "manager",
        }

        fallback = fallback_map.get(target)
        if fallback and fallback in available:
            return fallback

        # 最後回退：使用第一個可用角色
        if "developer" in available:
            return "developer"
        if "manager" in available:
            return "manager"
        return next(iter(available), None) if available else None

    def _pick_best_role(
        self,
        goal: str,
        available: set[str],
    ) -> str:
        """根據目標內容選擇最佳執行角色。"""
        goal_lower = goal.lower()

        role_keywords: list[tuple[list[str], str]] = [
            (["ui", "設計", "design", "wireframe", "佈局", "layout", "視覺"], "ui_designer"),
            (["css", "樣式", "style", "動畫", "animation", "rwd", "響應式"], "css_dev"),
            (["js", "javascript", "前端", "frontend", "react", "vue", "互動", "狀態"], "js_dev"),
            (["api", "後端", "backend", "資料庫", "database", "sql", "server"], "backend_dev"),
            (["測試", "test", "qa", "品質", "bug"], "tester"),
            (["架構", "architect", "設計", "系統"], "architect"),
            (["部署", "deploy", "ci/cd", "docker", "k8s", "維運"], "devops"),
            (["分析", "analyst", "研究", "research", "報告", "report"], "analyst"),
            (["審查", "review", "檢查"], "reviewer"),
            (["量化", "估值", "pe", "股票", "行情", "回測", "夏普", "外匯", "加密"], "quant_analyst"),
            (["opc", "工業", "產線", "標籤"], "opc_engineer"),
            (["爬蟲", "crawl", "採集"], "crawler"),
            (["故事", "情節", "對白", "story"], "story_writer"),
            (["rag", "檢索增強", "切片"], "rag_engineer"),
            (["評測", "eval", "基準"], "eval_engineer"),
            (["機器學習", "ml", "訓練"], "ml_engineer"),
            (["負載", "壓測", "吞吐"], "load_tester"),
            (["滲透", "弱點", "攻擊面"], "pen_tester"),
            (["plc", "連鎖"], "plc_engineer"),
            (["路由", "failover", "熔斷"], "router_eng"),
        ]

        for keywords, role in role_keywords:
            if any(kw in goal_lower for kw in keywords):
                if role in available:
                    return role
                # 嘗試回退
                fallback = self._find_closest_role(role, available)
                if fallback:
                    return fallback

        # 預設角色
        if "developer" in available:
            return "developer"
        return next(iter(available), "developer")