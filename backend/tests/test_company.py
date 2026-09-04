"""Phase 6+：公司運行時單元測試。

驗證：
1. 狀態模型（WorkItem 狀態機、CompanyConfig）
2. 預算控制（BudgetManager、TierRouter、CostTracker）
3. 工作項管理（WorkItemManager、依賴解析、看板）
4. 角色定義（內建模板）
5. 協調器（任務分解、執行-審查迴圈、整合）
6. EvoLoop 圖整合（公司模式路由）
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.company.budget import BudgetManager, CostTracker, TierRouter
from backend.company.decomposer import (
    DecompositionResult,
    DecompositionStrategy,
    TaskDecomposer,
)
from backend.company.prompts import (
    PAGE_DEV_TEMPLATE,
    PromptConfig,
)
from backend.company.roles import (
    BUILTIN_TEMPLATES,
    ROLE_MANAGER,
    STANDARD_ROLES,
)
from backend.company.state import (
    BudgetConfig,
    BudgetTier,
    CompanyConfig,
    RoleType,
    WorkItem,
    WorkItemStatus,
)
from backend.company.work_item import WorkItemManager

# ═══════════════════════════════════════════════════════════════
# 1. 狀態模型測試
# ═══════════════════════════════════════════════════════════════

class TestWorkItemStateMachine:
    """工作項狀態機測試。"""

    def test_initial_status_is_planning(self):
        item = WorkItem(title="測試任務")
        assert item.status == WorkItemStatus.PLANNING

    def test_valid_transition_planning_to_ready(self):
        item = WorkItem(title="測試")
        assert item.transition_to(WorkItemStatus.READY) is True
        assert item.status == WorkItemStatus.READY

    def test_invalid_transition_planning_to_done(self):
        item = WorkItem(title="測試")
        assert item.transition_to(WorkItemStatus.DONE) is False
        assert item.status == WorkItemStatus.PLANNING

    def test_full_lifecycle(self):
        """完整生命週期：PLANNING → READY → EXECUTING → IN_REVIEW → DONE。"""
        item = WorkItem(title="完整流程")
        assert item.transition_to(WorkItemStatus.READY)
        assert item.transition_to(WorkItemStatus.EXECUTING)
        assert item.transition_to(WorkItemStatus.IN_REVIEW)
        assert item.transition_to(WorkItemStatus.DONE)
        assert item.status == WorkItemStatus.DONE
        assert item.completed_at is not None

    def test_review_rework_cycle(self):
        """審查-修改迴圈：IN_REVIEW → REWORK → EXECUTING → IN_REVIEW → DONE。"""
        item = WorkItem(title="審查修改")
        item.transition_to(WorkItemStatus.READY)
        item.transition_to(WorkItemStatus.EXECUTING)
        item.transition_to(WorkItemStatus.IN_REVIEW)
        # 審查不通過
        assert item.transition_to(WorkItemStatus.REWORK)
        assert item.status == WorkItemStatus.REWORK
        # 修改後重新提交
        assert item.transition_to(WorkItemStatus.EXECUTING)
        assert item.transition_to(WorkItemStatus.IN_REVIEW)
        assert item.transition_to(WorkItemStatus.DONE)

    def test_done_is_terminal(self):
        """DONE 是終態，不可再轉換。"""
        item = WorkItem(title="完成")
        item.transition_to(WorkItemStatus.READY)
        item.transition_to(WorkItemStatus.EXECUTING)
        item.transition_to(WorkItemStatus.IN_REVIEW)
        item.transition_to(WorkItemStatus.DONE)
        assert item.transition_to(WorkItemStatus.REWORK) is False

    def test_block_and_unblock(self):
        """阻塞與解除阻塞。"""
        item = WorkItem(title="阻塞測試")
        item.transition_to(WorkItemStatus.READY)
        item.transition_to(WorkItemStatus.EXECUTING)
        assert item.transition_to(WorkItemStatus.BLOCKED)
        assert item.status == WorkItemStatus.BLOCKED
        assert item.transition_to(WorkItemStatus.READY)
        assert item.status == WorkItemStatus.READY


# ═══════════════════════════════════════════════════════════════
# 2. 預算控制測試
# ═══════════════════════════════════════════════════════════════

class TestCostTracker:
    """成本估算測試。"""

    def test_estimate_known_model(self):
        cost = CostTracker.estimate_cost("gpt-4o", input_tokens=1000, output_tokens=1000)
        # gpt-4o: (2.50 + 10.00) / 1M * 1000 ≈ 0.0125
        assert 0.01 < cost < 0.02

    def test_estimate_unknown_model_fallback(self):
        cost = CostTracker.estimate_cost("unknown-model", input_tokens=1000, output_tokens=1000)
        assert cost > 0

    def test_estimate_cost_rough(self):
        cost = CostTracker.estimate_cost_rough("gpt-4o-mini", "medium")
        # gpt-4o-mini: (0.15 + 0.60) / 1M * 2000 ≈ 0.0015
        assert 0.0001 < cost < 0.01


class TestTierRouter:
    """模型層級路由測試。"""

    def test_select_tier_routine(self):
        router = TierRouter(BudgetConfig())
        tier = router.select_tier("medium")
        assert tier == BudgetTier.ROUTINE

    def test_select_tier_critical(self):
        router = TierRouter(BudgetConfig())
        tier = router.select_tier("low", is_critical=True)
        assert tier == BudgetTier.CRITICAL

    def test_resolve_model_normal(self, monkeypatch):
        # 隔離 LLM 配置：無顯式配置時使用傳統多模型層級預設
        monkeypatch.setattr("backend.core.llm_config.get_explicit_model", lambda: "")
        router = TierRouter(BudgetConfig())
        model = router.resolve_model(BudgetTier.ROUTINE, budget_pressure=0.0)
        assert model == "gpt-4o-mini"

    def test_resolve_model_degraded(self):
        config = BudgetConfig(
            degrade_chain={BudgetTier.CRITICAL: "gpt-4o-mini"}
        )
        router = TierRouter(config)
        model = router.resolve_model(BudgetTier.CRITICAL, budget_pressure=0.95)
        assert model == "gpt-4o-mini"  # 降級


class TestBudgetManager:
    """預算管理器測試。"""

    def test_initial_budget_pressure_zero(self):
        bm = BudgetManager(BudgetConfig())
        assert bm.budget_pressure == 0.0

    def test_record_cost_updates_pressure(self):
        config = BudgetConfig(task_limit_usd=1.0)
        bm = BudgetManager(config)
        bm.record_cost(0.5)
        assert bm.task_spent == 0.5
        assert bm.budget_pressure == 0.5

    def test_budget_pressure_takes_max(self):
        config = BudgetConfig(task_limit_usd=1.0, session_limit_usd=10.0)
        bm = BudgetManager(config)
        bm.record_cost(0.9)  # 90% of task, 9% of session
        assert bm.budget_pressure == 0.9

    def test_can_afford_within_budget(self):
        config = BudgetConfig(task_limit_usd=1.0)
        bm = BudgetManager(config)
        can, reason = bm.can_afford(0.5, BudgetTier.ROUTINE)
        assert can is True

    def test_can_afford_exceeds_task_budget_hard_stop(self):
        config = BudgetConfig(task_limit_usd=1.0, hard_stop=True)
        bm = BudgetManager(config)
        bm.record_cost(0.9)
        can, reason = bm.can_afford(0.2, BudgetTier.ROUTINE)
        assert can is False

    def test_can_afford_exceeds_soft_limit(self):
        config = BudgetConfig(task_limit_usd=1.0, hard_stop=False)
        bm = BudgetManager(config)
        bm.record_cost(0.9)
        can, reason = bm.can_afford(0.5, BudgetTier.ROUTINE)
        assert can is True  # 軟限制，仍可繼續但降級

    def test_reset_task(self):
        config = BudgetConfig(task_limit_usd=1.0)
        bm = BudgetManager(config)
        bm.record_cost(0.5)
        bm.reset_task()
        assert bm.task_spent == 0.0

    def test_resolve_model_for_tier(self, monkeypatch):
        # 隔離 LLM 配置：無顯式配置時使用傳統多模型層級預設
        monkeypatch.setattr("backend.core.llm_config.get_explicit_model", lambda: "")
        bm = BudgetManager(BudgetConfig())
        model = bm.resolve_model_for_tier(BudgetTier.ROUTINE)
        assert model == "gpt-4o-mini"

    def test_to_dict(self):
        bm = BudgetManager(BudgetConfig(task_limit_usd=1.0))
        d = bm.to_dict()
        assert "task_spent" in d
        assert "budget_pressure" in d


# ═══════════════════════════════════════════════════════════════
# 3. 工作項管理測試
# ═══════════════════════════════════════════════════════════════

class TestWorkItemManager:
    """工作項管理器測試。"""

    def test_create_work_item(self):
        wm = WorkItemManager()
        item = wm.create("任務 A", "描述 A", assignee=RoleType.DEVELOPER)
        assert item.title == "任務 A"
        assert item.status == WorkItemStatus.PLANNING

    def test_decompose_creates_ready_items(self):
        wm = WorkItemManager()
        subtasks = [
            {"title": "子任務 1", "description": "desc1"},
            {"title": "子任務 2", "description": "desc2"},
        ]
        items = wm.decompose("目標", subtasks, assignee=RoleType.DEVELOPER)
        assert len(items) == 2
        for item in items:
            assert item.status == WorkItemStatus.READY

    def test_dependency_resolution(self):
        """依賴解析：只有當依賴完成時，工作項才就緒。"""
        wm = WorkItemManager()
        item_a = wm.create("A", assignee=RoleType.DEVELOPER)
        item_a.transition_to(WorkItemStatus.READY)
        item_b = wm.create("B", assignee=RoleType.DEVELOPER, depends_on=[item_a.id])
        item_b.transition_to(WorkItemStatus.READY)

        # A 未完成，B 不應出現在就緒列表
        ready = wm.get_ready_items()
        ready_ids = [r.id for r in ready]
        assert item_a.id in ready_ids
        assert item_b.id not in ready_ids  # 依賴未滿足

        # 完成 A 後，B 應該就緒
        item_a.transition_to(WorkItemStatus.EXECUTING)
        item_a.transition_to(WorkItemStatus.IN_REVIEW)
        item_a.transition_to(WorkItemStatus.DONE)

        ready = wm.get_ready_items()
        ready_ids = [r.id for r in ready]
        assert item_b.id in ready_ids

    def test_kanban_view(self):
        wm = WorkItemManager()
        wm.create("任務 1", assignee=RoleType.DEVELOPER)
        wm.create("任務 2", assignee=RoleType.REVIEWER)

        kanban = wm.get_kanban()
        assert len(kanban[WorkItemStatus.PLANNING]) == 2

    def test_stats(self):
        wm = WorkItemManager()
        item = wm.create("任務")
        item.transition_to(WorkItemStatus.READY)
        item.transition_to(WorkItemStatus.EXECUTING)
        item.transition_to(WorkItemStatus.IN_REVIEW)
        item.transition_to(WorkItemStatus.DONE)

        stats = wm.get_stats()
        assert stats["total"] == 1
        assert stats["done"] == 1
        assert stats["completion_pct"] == 100.0

    def test_has_work_remaining(self):
        wm = WorkItemManager()
        assert wm.has_work_remaining() is False

        item = wm.create("任務")
        item.transition_to(WorkItemStatus.READY)
        assert wm.has_work_remaining() is True

        item.transition_to(WorkItemStatus.EXECUTING)
        item.transition_to(WorkItemStatus.IN_REVIEW)
        item.transition_to(WorkItemStatus.DONE)
        assert wm.has_work_remaining() is False


# ═══════════════════════════════════════════════════════════════
# 4. 角色定義測試
# ═══════════════════════════════════════════════════════════════

class TestRoles:
    """角色定義測試。"""

    def test_standard_roles_have_all_types(self):
        for role_type in RoleType:
            assert role_type in STANDARD_ROLES

    def test_manager_can_delegate(self):
        assert RoleType.DEVELOPER in ROLE_MANAGER.can_delegate_to
        assert RoleType.REVIEWER in ROLE_MANAGER.can_delegate_to

    def test_builtin_templates_exist(self):
        assert "fullstack_app" in BUILTIN_TEMPLATES
        assert "research_report" in BUILTIN_TEMPLATES
        assert "quick_task" in BUILTIN_TEMPLATES
        assert "full_company" in BUILTIN_TEMPLATES

    def test_fullstack_team_has_expected_roles(self):
        config = BUILTIN_TEMPLATES["fullstack_app"]
        assert RoleType.MANAGER in config.roles
        assert RoleType.TECH_LEAD in config.roles
        assert RoleType.JS_DEV in config.roles
        assert RoleType.CSS_DEV in config.roles
        assert RoleType.BACKEND_DEV in config.roles
        assert RoleType.REVIEWER in config.roles
        assert RoleType.SYNTHESIZER in config.roles
        assert config.max_parallel_workers == 4

    def test_quick_task_has_lower_budget(self):
        config = BUILTIN_TEMPLATES["quick_task"]
        assert config.budget.task_limit_usd == 0.5
        assert config.budget.session_limit_usd == 2.0


# ═══════════════════════════════════════════════════════════════
# 5. 協調器測試（模擬 LLM 呼叫）
# ═══════════════════════════════════════════════════════════════

FAKE_DECOMPOSE_RESPONSE = json.dumps({
    "subtasks": [
        {
            "title": "分析需求",
            "description": "分析使用者需求並產出規格",
            "assignee": "analyst",
            "depends_on": [],
            "complexity": "medium",
        },
        {
            "title": "實作功能",
            "description": "根據規格實作核心功能",
            "assignee": "developer",
            "depends_on": [0],
            "complexity": "high",
        },
    ]
})

# 預建 DecompositionResult（供 mock TaskDecomposer 使用）
FAKE_DECOMPOSE_RESULT = DecompositionResult(
    goal="",
    strategy=DecompositionStrategy.LLM,
    subtasks=[
        {"title": "分析需求", "description": "分析使用者需求並產出規格",
         "assignee": "analyst", "depends_on": [], "complexity": "medium"},
        {"title": "實作功能", "description": "根據規格實作核心功能",
         "assignee": "developer", "depends_on": [0], "complexity": "high"},
    ],
    execution_plan="並行執行：先分析後實作",
)

FAKE_SINGLE_RESULT = DecompositionResult(
    goal="",
    strategy=DecompositionStrategy.LLM,
    subtasks=[
        {"title": "任務", "assignee": "developer", "depends_on": [], "complexity": "medium"}
    ],
    execution_plan="單一任務",
)

FAKE_LOW_RESULT = DecompositionResult(
    goal="",
    strategy=DecompositionStrategy.LLM,
    subtasks=[
        {"title": "任務", "assignee": "developer", "depends_on": [], "complexity": "low"}
    ],
    execution_plan="簡單任務",
)

FAKE_EXECUTE_RESPONSE = "這是實作結果：完成了功能開發。"

FAKE_REVIEW_APPROVED = json.dumps({
    "approved": True,
    "score": 8,
    "strengths": "完整且清晰",
    "weaknesses": "",
    "feedback": "",
})

FAKE_REVIEW_REWORK = json.dumps({
    "approved": False,
    "score": 5,
    "strengths": "方向正確",
    "weaknesses": "缺少細節",
    "feedback": "請補充更多實作細節",
})

FAKE_SYNTHESIZE = "整合結果：需求分析完成，功能實作完成。"

FAKE_FINAL_REVIEW = json.dumps({
    "approved": True,
    "summary": "專案成功完成",
    "key_decisions": ["使用模組化架構"],
    "recommendations": ["建議加入更多測試"],
    "lessons_learned": "分工明確提升效率",
})


# ═══════════════════════════════════════════════════════════════
# 共享 Fixtures
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def mock_llm_sequence():
    """模擬 LLM 呼叫序列：執行x2 → 審查x2 → 整合 → 最終審查。

    注意：分解階段已由 TaskDecomposer mock 處理，不再經過 call_llm。
    """
    return [
        FAKE_EXECUTE_RESPONSE,     # 執行工作項 0
        FAKE_REVIEW_APPROVED,       # 審查工作項 0
        FAKE_EXECUTE_RESPONSE,     # 執行工作項 1
        FAKE_REVIEW_APPROVED,       # 審查工作項 1
        FAKE_SYNTHESIZE,            # 整合
        FAKE_FINAL_REVIEW,          # 最終審查
    ]


# ═══════════════════════════════════════════════════════════════
# 5. 公司協調器測試
# ═══════════════════════════════════════════════════════════════

class TestCompanyOrchestrator:
    """公司協調器測試（使用 mock LLM + mock TaskDecomposer）。"""

    @pytest.mark.asyncio
    async def test_execute_full_flow(self, mock_llm_sequence):
        """完整公司運行流程（模擬 LLM + TaskDecomposer）。"""
        from backend.company.orchestrator import CompanyOrchestrator
        from backend.company.roles import create_full_company

        config = create_full_company()
        orchestrator = CompanyOrchestrator(config)

        with patch.object(
            orchestrator.decomposer, "decompose",
            new_callable=AsyncMock,
            return_value=FAKE_DECOMPOSE_RESULT,
        ), patch(
            "backend.company.orchestrator.call_llm",
            side_effect=mock_llm_sequence,
        ):
            result = await orchestrator.execute("建立一個用戶管理系統")

        assert result["success"] is True
        assert "final_output" in result
        assert "kanban" in result
        assert "budget" in result
        assert "stats" in result
        assert result["stats"]["done"] > 0

    @pytest.mark.asyncio
    async def test_execute_with_review_rework(self):
        """審查-修改迴圈：第一次審查不通過，修改後通過。"""
        from backend.company.orchestrator import CompanyOrchestrator

        config = BUILTIN_TEMPLATES["quick_task"]
        orchestrator = CompanyOrchestrator(config)

        responses = [
            FAKE_EXECUTE_RESPONSE,
            FAKE_REVIEW_REWORK,       # 第一次審查：不通過
            FAKE_EXECUTE_RESPONSE,    # 修改後重新執行
            FAKE_REVIEW_APPROVED,     # 第二次審查：通過
            FAKE_SYNTHESIZE,
            FAKE_FINAL_REVIEW,
        ]

        with patch.object(
            orchestrator.decomposer, "decompose",
            new_callable=AsyncMock,
            return_value=FAKE_SINGLE_RESULT,
        ), patch(
            "backend.company.orchestrator.call_llm",
            side_effect=responses,
        ):
            result = await orchestrator.execute("簡單任務")

        assert result["success"] is True
        stats = result["stats"]
        assert stats["done"] == 1

    @pytest.mark.asyncio
    async def test_execute_with_decompose_failure(self):
        """TaskDecomposer 分解失敗時的回退處理。"""
        from backend.company.orchestrator import CompanyOrchestrator

        config = BUILTIN_TEMPLATES["quick_task"]
        orchestrator = CompanyOrchestrator(config)

        empty_result = DecompositionResult(
            goal="", strategy=DecompositionStrategy.LLM, subtasks=[]
        )

        with patch.object(
            orchestrator.decomposer, "decompose",
            new_callable=AsyncMock,
            return_value=empty_result,
        ):
            result = await orchestrator.execute("測試")

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_budget_tracking_during_execution(self):
        """執行過程中預算被正確追蹤。"""
        from backend.company.orchestrator import CompanyOrchestrator

        config = BUILTIN_TEMPLATES["quick_task"]
        orchestrator = CompanyOrchestrator(config)

        responses = [
            FAKE_EXECUTE_RESPONSE,
            FAKE_REVIEW_APPROVED,
            FAKE_SYNTHESIZE,
            FAKE_FINAL_REVIEW,
        ]

        with patch.object(
            orchestrator.decomposer, "decompose",
            new_callable=AsyncMock,
            return_value=FAKE_LOW_RESULT,
        ), patch(
            "backend.company.orchestrator.call_llm",
            side_effect=responses,
        ):
            result = await orchestrator.execute("測試")

        budget = result["budget"]
        assert budget["task_spent"] > 0
        assert budget["budget_pressure"] >= 0

    def test_get_kanban_empty(self):
        """空看板。"""
        from backend.company.orchestrator import CompanyOrchestrator

        orchestrator = CompanyOrchestrator(BUILTIN_TEMPLATES["quick_task"])
        kanban = orchestrator.get_kanban()
        assert all(len(items) == 0 for items in kanban.values())

    def test_get_budget_status(self):
        """預算狀態查詢。"""
        from backend.company.orchestrator import CompanyOrchestrator

        orchestrator = CompanyOrchestrator(BUILTIN_TEMPLATES["quick_task"])
        status = orchestrator.get_budget_status()
        assert "task_spent" in status
        assert "budget_pressure" in status


# ═══════════════════════════════════════════════════════════
# 5.5 執行軌跡診斷測試（run_id + 持久 sink + 降級標記）
# ═══════════════════════════════════════════════════════════

def _read_run_sink(run_id: str) -> list[dict]:
    """讀取指定 run 的持久 JSONL 軌跡（conftest 已將目錄隔離至暫存）。"""
    from backend.company.run_log import run_log_path

    path = run_log_path(run_id)
    assert path.exists(), f"持久軌跡檔案不存在：{path}"
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class TestCompanyRunTrace:
    """公司執行軌跡測試：run_id 關聯、持久 sink、降級路徑標記。"""

    @pytest.mark.asyncio
    async def test_full_flow_run_id_persisted_to_sink(self):
        """完整流程：所有事件帶同一 run_id，進程結束後仍可從 sink 讀回。"""
        from backend.company.orchestrator import CompanyOrchestrator

        config = BUILTIN_TEMPLATES["quick_task"]
        orchestrator = CompanyOrchestrator(config)

        responses = [
            FAKE_EXECUTE_RESPONSE,
            FAKE_REVIEW_APPROVED,
            FAKE_SYNTHESIZE,
            FAKE_FINAL_REVIEW,
        ]

        with patch.object(
            orchestrator.decomposer, "decompose",
            new_callable=AsyncMock,
            return_value=FAKE_SINGLE_RESULT,
        ), patch(
            "backend.company.orchestrator.call_llm",
            side_effect=responses,
        ):
            result = await orchestrator.execute("簡單任務")

        run_id = result["run_id"]
        assert run_id
        # 記憶體 run_log 中所有事件共享同一 run_id
        assert result["run_log"]
        assert all(entry["run_id"] == run_id for entry in result["run_log"])

        # 持久 sink：進程結束後仍可讀回帶 run_id 的關鍵事件
        records = _read_run_sink(run_id)
        assert all(r["run_id"] == run_id for r in records)
        events = [r["event"] for r in records]
        assert "company_start" in events
        assert "company_done" in events

    @pytest.mark.asyncio
    async def test_review_force_done_degraded_recorded(self):
        """降級路徑 1：達到最大審查輪數強制完成，事件帶 degraded 且持久化。"""
        from backend.company.events import CompanyEvent
        from backend.company.orchestrator import CompanyOrchestrator

        config = BUILTIN_TEMPLATES["quick_task"]  # max_review_rounds=2
        orchestrator = CompanyOrchestrator(config)

        captured: list[tuple] = []
        orchestrator.events.on(lambda e, d: captured.append((e, d)))

        responses = [
            FAKE_EXECUTE_RESPONSE,
            FAKE_REVIEW_REWORK,       # 第 1 輪審查：不通過
            FAKE_EXECUTE_RESPONSE,    # 修改
            FAKE_REVIEW_REWORK,       # 第 2 輪審查：仍不通過
            FAKE_EXECUTE_RESPONSE,    # 修改
            FAKE_SYNTHESIZE,
            FAKE_FINAL_REVIEW,
        ]

        with patch.object(
            orchestrator.decomposer, "decompose",
            new_callable=AsyncMock,
            return_value=FAKE_SINGLE_RESULT,
        ), patch(
            "backend.company.orchestrator.call_llm",
            side_effect=responses,
        ):
            result = await orchestrator.execute("審查永遠不通過的任務")

        run_id = result["run_id"]

        # run_log 中有顯式 degraded 標記
        force = [e for e in result["run_log"] if e["event"] == "review_force_done"]
        assert len(force) == 1
        assert force[0]["degraded"] is True
        assert force[0]["run_id"] == run_id

        # EventBus 事件同樣帶 degraded 標記
        bus_events = [d for e, d in captured if e == CompanyEvent.REVIEW_FORCE_DONE]
        assert bus_events
        assert bus_events[0]["degraded"] is True

        # 持久 sink 中可見帶 run_id 的降級事件
        records = _read_run_sink(run_id)
        degraded = [r for r in records if r["event"] == "review_force_done"]
        assert degraded
        assert all(r["degraded"] is True and r["run_id"] == run_id for r in degraded)

    @pytest.mark.asyncio
    async def test_final_review_exception_degraded_recorded(self):
        """降級路徑 2：最終審查異常自動通過，事件帶 degraded 且持久化。"""
        from backend.company.events import CompanyEvent
        from backend.company.orchestrator import CompanyOrchestrator

        config = BUILTIN_TEMPLATES["quick_task"]
        orchestrator = CompanyOrchestrator(config)

        captured: list[tuple] = []
        orchestrator.events.on(lambda e, d: captured.append((e, d)))

        responses = [
            FAKE_EXECUTE_RESPONSE,
            FAKE_REVIEW_APPROVED,
            FAKE_SYNTHESIZE,
            RuntimeError("最終審查 LLM 呼叫失敗"),  # 最終審查階段拋出異常
        ]

        with patch.object(
            orchestrator.decomposer, "decompose",
            new_callable=AsyncMock,
            return_value=FAKE_SINGLE_RESULT,
        ), patch(
            "backend.company.orchestrator.call_llm",
            side_effect=responses,
        ):
            result = await orchestrator.execute("最終審查會失敗的任務")

        run_id = result["run_id"]

        # 自動通過但帶 degraded 標記
        review = result["review"]
        assert review["approved"] is True
        assert review["degraded"] is True
        assert "error" in review

        # run_log 中記錄降級事件
        degraded_events = [
            e for e in result["run_log"] if e["event"] == "final_review_degraded"
        ]
        assert len(degraded_events) == 1
        assert degraded_events[0]["degraded"] is True
        assert degraded_events[0]["run_id"] == run_id

        # EventBus 與持久 sink 均可見帶 run_id 的降級事件
        bus_events = [d for e, d in captured if e == CompanyEvent.FINAL_REVIEW_DEGRADED]
        assert bus_events and bus_events[0]["degraded"] is True

        records = _read_run_sink(run_id)
        sink_degraded = [
            r for r in records if r["event"] == "final_review_degraded"
        ]
        assert sink_degraded
        assert all(
            r["degraded"] is True and r["run_id"] == run_id for r in sink_degraded
        )


# ═══════════════════════════════════════════════════════════════
# 6. TaskDecomposer 測試（主功能模組）
# ═══════════════════════════════════════════════════════════════

class TestTaskDecomposerTemplate:
    """模板驅動拆分測試。"""

    def test_page_dev_template_matches_keywords(self):
        """頁面相關關鍵字應匹配 PAGE_DEV_TEMPLATE。"""
        from backend.company.budget import BudgetManager
        from backend.company.decomposer import TaskDecomposer

        config = BUILTIN_TEMPLATES["page_dev"]
        bm = BudgetManager(config.budget)
        decomposer = TaskDecomposer(config, bm)

        for keyword in ["頁面", "ui", "前端", "web", "網頁"]:
            result = decomposer._template_decompose(f"開發一個{keyword}")
            assert result.strategy == DecompositionStrategy.TEMPLATE
            assert len(result.subtasks) >= 3

    def test_template_decompose_falls_back_to_rule(self):
        """無匹配模板時降級為 RULE 策略。"""
        from backend.company.budget import BudgetManager
        from backend.company.decomposer import TaskDecomposer

        config = BUILTIN_TEMPLATES["quick_task"]
        bm = BudgetManager(config.budget)
        decomposer = TaskDecomposer(config, bm)

        result = decomposer._template_decompose("做一件完全不相關的事")
        assert result.strategy == DecompositionStrategy.RULE

    def test_template_filters_unavailable_roles(self):
        """模板應過濾團隊中不存在的角色。"""
        from backend.company.budget import BudgetManager
        from backend.company.decomposer import TaskDecomposer

        # quick_task 只有 manager + developer
        config = BUILTIN_TEMPLATES["quick_task"]
        bm = BudgetManager(config.budget)
        decomposer = TaskDecomposer(config, bm)

        # page_dev 模板有 ui_designer 等角色，但 quick_task 沒有
        result = decomposer._template_decompose("開發一個頁面")
        # 應該有替換/過濾邏輯
        for task in result.subtasks:
            role = task.get("assignee", "")
            assert role in ("manager", "developer", "analyst", "reviewer", "")


class TestTaskDecomposerRule:
    """規則驅動拆分測試。"""

    def test_rule_simple_goal_single_task(self):
        """簡單目標（少於 30 字）產生單一工作項。"""
        from backend.company.budget import BudgetManager
        from backend.company.decomposer import TaskDecomposer

        config = BUILTIN_TEMPLATES["quick_task"]
        bm = BudgetManager(config.budget)
        decomposer = TaskDecomposer(config, bm)

        result = decomposer._rule_decompose("寫一個 hello world")
        assert result.strategy == DecompositionStrategy.RULE
        assert len(result.subtasks) == 1

    def test_rule_medium_goal_two_tasks(self):
        """中等目標（30-100 字）產生兩個工作項。"""
        from backend.company.budget import BudgetManager
        from backend.company.decomposer import TaskDecomposer

        config = BUILTIN_TEMPLATES["quick_task"]
        bm = BudgetManager(config.budget)
        decomposer = TaskDecomposer(config, bm)

        goal = "建立一個完整的用戶管理系統，包含註冊、登入、權限管理等功能模組"
        result = decomposer._rule_decompose(goal)
        assert result.strategy == DecompositionStrategy.RULE
        assert len(result.subtasks) >= 2

    def test_rule_picks_best_role(self):
        """規則拆分應根據目標關鍵字選擇最佳角色。"""
        from backend.company.budget import BudgetManager
        from backend.company.decomposer import TaskDecomposer

        config = BUILTIN_TEMPLATES["page_dev"]
        bm = BudgetManager(config.budget)
        decomposer = TaskDecomposer(config, bm)

        # 前端相關關鍵字
        result = decomposer._rule_decompose("設計一個 UI 頁面")
        assert result.subtasks[0]["assignee"] in ("ui_designer", "js_dev", "developer")

        # 後端相關關鍵字
        result = decomposer._rule_decompose("開發一個 API 端點")
        assert result.subtasks[0]["assignee"] in ("backend_dev", "developer")


class TestTaskDecomposerAutoSelect:
    """自動策略選擇測試。"""

    def test_auto_selects_template_for_page_dev(self):
        """頁面開發目標應自動選擇 TEMPLATE 策略。"""
        from backend.company.budget import BudgetManager
        from backend.company.decomposer import TaskDecomposer

        config = BUILTIN_TEMPLATES["page_dev"]
        bm = BudgetManager(config.budget)
        decomposer = TaskDecomposer(config, bm)

        strategy = decomposer._select_strategy("開發一個用戶登入頁面")
        assert strategy == DecompositionStrategy.TEMPLATE

    def test_auto_selects_llm_for_unknown_goal(self):
        """未知目標應選擇 LLM 策略。"""
        from backend.company.budget import BudgetManager
        from backend.company.decomposer import TaskDecomposer

        config = BUILTIN_TEMPLATES["quick_task"]
        bm = BudgetManager(config.budget)
        decomposer = TaskDecomposer(config, bm)

        strategy = decomposer._select_strategy("做一些完全不相關的事情xyz")
        assert strategy == DecompositionStrategy.LLM

    def test_auto_selects_rule_under_budget_pressure(self):
        """預算壓力高時應降級為 RULE 策略。"""
        from backend.company.budget import BudgetManager
        from backend.company.decomposer import TaskDecomposer

        config = BUILTIN_TEMPLATES["page_dev"]
        bm = BudgetManager(config.budget)
        bm._task_spent = config.budget.task_limit_usd * 0.95  # 95% 壓力
        decomposer = TaskDecomposer(config, bm)

        strategy = decomposer._select_strategy("開發一個頁面")
        assert strategy == DecompositionStrategy.RULE


class TestTaskDecomposerBuildItems:
    """build_work_items 與依賴解析測試。"""

    def test_build_work_items_creates_correct_count(self):
        """應建立正確數量的工作項。"""
        from backend.company.budget import BudgetManager
        from backend.company.decomposer import TaskDecomposer
        from backend.company.work_item import WorkItemManager

        config = BUILTIN_TEMPLATES["page_dev"]
        bm = BudgetManager(config.budget)
        wm = WorkItemManager()
        decomposer = TaskDecomposer(config, bm, wm)

        result = DecompositionResult(
            goal="測試",
            strategy=DecompositionStrategy.TEMPLATE,
            subtasks=[
                {"title": "任務A", "assignee": "developer", "depends_on": [], "complexity": "low"},
                {"title": "任務B", "assignee": "tester", "depends_on": [0], "complexity": "medium"},
            ],
        )

        items = decomposer.build_work_items(result)
        assert len(items) == 2
        assert items[0].status == WorkItemStatus.READY
        assert items[1].status == WorkItemStatus.READY

    def test_build_work_items_resolves_dependencies(self):
        """應正確解析索引式依賴為實際 ID。"""
        from backend.company.budget import BudgetManager
        from backend.company.decomposer import TaskDecomposer
        from backend.company.work_item import WorkItemManager

        config = BUILTIN_TEMPLATES["page_dev"]
        bm = BudgetManager(config.budget)
        wm = WorkItemManager()
        decomposer = TaskDecomposer(config, bm, wm)

        result = DecompositionResult(
            goal="測試",
            strategy=DecompositionStrategy.TEMPLATE,
            subtasks=[
                {"title": "任務A", "assignee": "developer", "depends_on": [], "complexity": "low"},
                {"title": "任務B", "assignee": "tester", "depends_on": [0], "complexity": "medium"},
                {"title": "任務C", "assignee": "reviewer", "depends_on": [0, 1], "complexity": "low"},
            ],
        )

        items = decomposer.build_work_items(result)
        assert len(items) == 3
        assert items[0].depends_on == []  # 無依賴
        assert items[1].depends_on == [items[0].id]  # 依賴任務A
        assert items[2].depends_on == [items[0].id, items[1].id]  # 依賴任務A和B

    def test_build_work_items_maps_complexity_to_tier(self):
        """複雜度應正確映射到預算層級。"""
        from backend.company.budget import BudgetManager
        from backend.company.decomposer import TaskDecomposer
        from backend.company.work_item import WorkItemManager

        config = BUILTIN_TEMPLATES["page_dev"]
        bm = BudgetManager(config.budget)
        wm = WorkItemManager()
        decomposer = TaskDecomposer(config, bm, wm)

        result = DecompositionResult(
            goal="測試",
            strategy=DecompositionStrategy.TEMPLATE,
            subtasks=[
                {"title": "低", "assignee": "developer", "depends_on": [], "complexity": "low"},
                {"title": "中", "assignee": "developer", "depends_on": [], "complexity": "medium"},
                {"title": "高", "assignee": "developer", "depends_on": [], "complexity": "high"},
            ],
        )

        items = decomposer.build_work_items(result)
        assert items[0].tier == BudgetTier.SUMMARY
        assert items[1].tier == BudgetTier.ROUTINE
        assert items[2].tier == BudgetTier.REASONING


class TestTaskDecomposerParallelPlan:
    """並行執行規劃測試。"""

    def test_plan_parallel_no_dependencies(self):
        """無依賴時所有工作項應在同一階段。"""
        from backend.company.budget import BudgetManager
        from backend.company.decomposer import TaskDecomposer

        config = BUILTIN_TEMPLATES["page_dev"]
        bm = BudgetManager(config.budget)
        decomposer = TaskDecomposer(config, bm)

        subtasks = [
            {"title": "A", "depends_on": []},
            {"title": "B", "depends_on": []},
            {"title": "C", "depends_on": []},
        ]
        phases = decomposer.plan_parallel_execution(subtasks)
        assert len(phases) == 1
        assert len(phases[0]) == 3

    def test_plan_parallel_chain_dependencies(self):
        """鏈式依賴時應產生多個階段。"""
        from backend.company.budget import BudgetManager
        from backend.company.decomposer import TaskDecomposer

        config = BUILTIN_TEMPLATES["page_dev"]
        bm = BudgetManager(config.budget)
        decomposer = TaskDecomposer(config, bm)

        subtasks = [
            {"title": "A", "depends_on": []},
            {"title": "B", "depends_on": [0]},
            {"title": "C", "depends_on": [1]},
        ]
        phases = decomposer.plan_parallel_execution(subtasks)
        assert len(phases) == 3
        assert phases[0] == [0]
        assert phases[1] == [1]
        assert phases[2] == [2]

    def test_plan_parallel_mixed_dependencies(self):
        """混合依賴：A 和 B 平行，C 依賴 A 和 B。"""
        from backend.company.budget import BudgetManager
        from backend.company.decomposer import TaskDecomposer

        config = BUILTIN_TEMPLATES["page_dev"]
        bm = BudgetManager(config.budget)
        decomposer = TaskDecomposer(config, bm)

        subtasks = [
            {"title": "A", "depends_on": []},
            {"title": "B", "depends_on": []},
            {"title": "C", "depends_on": [0, 1]},
        ]
        phases = decomposer.plan_parallel_execution(subtasks)
        assert len(phases) == 2
        assert 0 in phases[0] and 1 in phases[0]  # A, B 平行
        assert phases[1] == [2]  # C 在下一階段

    def test_page_dev_template_phases(self):
        """PAGE_DEV_TEMPLATE 應有正確的階段結構（基於依賴拓樸）。"""
        from backend.company.budget import BudgetManager
        from backend.company.decomposer import TaskDecomposer

        config = BUILTIN_TEMPLATES["page_dev"]
        bm = BudgetManager(config.budget)
        decomposer = TaskDecomposer(config, bm)

        phases = decomposer.plan_parallel_execution(PAGE_DEV_TEMPLATE)
        # 依賴鏈：UI(0)+Arch(1) → Backend(2,dep on 1)+CSS(3,dep on 0) → JS(4,dep on 0,2) → Test(5,dep on 3,4) → Review(6,dep on 5)
        assert len(phases) == 5
        # Phase 1: UI 設計 + 架構設計（無依賴，平行）
        assert 0 in phases[0] and 1 in phases[0]
        # Phase 2: 後端 API + CSS（依賴 Phase 1）
        assert 2 in phases[1] and 3 in phases[1]
        # Phase 3: JS（依賴 Phase 1+2）
        assert 4 in phases[2]
        # Phase 4: 測試（依賴 Phase 3）
        assert 5 in phases[3]
        # Phase 5: 審查與整合（依賴 Phase 4）
        assert 6 in phases[4]


class TestTaskDecomposerLLM:
    """LLM 驅動拆分測試（使用 mock）。"""

    @pytest.mark.asyncio
    async def test_llm_decompose_with_mock(self):
        """LLM 拆分應正確解析回應。"""
        from backend.company.budget import BudgetManager
        from backend.company.decomposer import TaskDecomposer

        config = BUILTIN_TEMPLATES["page_dev"]
        bm = BudgetManager(config.budget)
        decomposer = TaskDecomposer(config, bm)

        with patch(
            "backend.company.decomposer.call_llm",
            return_value=FAKE_DECOMPOSE_RESPONSE,
        ):
            result = await decomposer._llm_decompose("建立一個用戶管理系統")

        assert result.strategy == DecompositionStrategy.LLM
        assert len(result.subtasks) == 2
        assert result.subtasks[0]["assignee"] == "analyst"
        assert result.subtasks[1]["assignee"] == "developer"

    @pytest.mark.asyncio
    async def test_llm_decompose_falls_back_to_rule(self):
        """LLM 失敗時應降級為 RULE 策略。"""
        from backend.company.budget import BudgetManager
        from backend.company.decomposer import TaskDecomposer

        config = BUILTIN_TEMPLATES["quick_task"]
        bm = BudgetManager(config.budget)
        decomposer = TaskDecomposer(config, bm)

        with patch(
            "backend.company.decomposer.call_llm",
            side_effect=RuntimeError("LLM 不可用"),
        ):
            result = await decomposer._llm_decompose("測試目標")

        # 應降級為 RULE
        assert result.strategy == DecompositionStrategy.RULE
        assert len(result.subtasks) >= 1

    @pytest.mark.asyncio
    async def test_decompose_with_explicit_strategy(self):
        """顯式指定策略時應使用該策略。"""
        from backend.company.budget import BudgetManager
        from backend.company.decomposer import TaskDecomposer

        config = BUILTIN_TEMPLATES["page_dev"]
        bm = BudgetManager(config.budget)
        decomposer = TaskDecomposer(config, bm)

        # 強制使用 RULE 策略
        result = await decomposer.decompose(
            "開發一個用戶登入頁面",
            strategy=DecompositionStrategy.RULE,
        )
        assert result.strategy == DecompositionStrategy.RULE

        # 強制使用 TEMPLATE 策略
        result = await decomposer.decompose(
            "開發一個頁面",
            strategy=DecompositionStrategy.TEMPLATE,
        )
        assert result.strategy == DecompositionStrategy.TEMPLATE


class TestTaskDecomposerHelpers:
    """輔助方法測試。"""

    def test_pick_best_role_ui(self):
        """UI 關鍵字應匹配 ui_designer。"""
        from backend.company.budget import BudgetManager
        from backend.company.decomposer import TaskDecomposer

        config = BUILTIN_TEMPLATES["page_dev"]
        bm = BudgetManager(config.budget)
        decomposer = TaskDecomposer(config, bm)

        available = set(rt.value for rt in config.roles)
        role = decomposer._pick_best_role("設計一個 UI 頁面佈局", available)
        assert role == "ui_designer"

    def test_pick_best_role_backend(self):
        """後端關鍵字應匹配 backend_dev。"""
        from backend.company.budget import BudgetManager
        from backend.company.decomposer import TaskDecomposer

        config = BUILTIN_TEMPLATES["page_dev"]
        bm = BudgetManager(config.budget)
        decomposer = TaskDecomposer(config, bm)

        available = set(rt.value for rt in config.roles)
        role = decomposer._pick_best_role("開發一個 REST API", available)
        assert role == "backend_dev"

    def test_find_closest_role_fallback(self):
        """角色不可用時應回退到通用角色。"""
        from backend.company.budget import BudgetManager
        from backend.company.decomposer import TaskDecomposer

        config = BUILTIN_TEMPLATES["quick_task"]
        bm = BudgetManager(config.budget)
        decomposer = TaskDecomposer(config, bm)

        # quick_task 只有 manager + developer
        available = set(rt.value for rt in config.roles)
        result = decomposer._find_closest_role("ui_designer", available)
        assert result == "developer"

    def test_format_org_chart(self):
        """組織架構格式化應正確輸出樹狀結構。"""
        from backend.company.budget import BudgetManager
        from backend.company.decomposer import TaskDecomposer

        config = BUILTIN_TEMPLATES["page_dev"]
        bm = BudgetManager(config.budget)
        decomposer = TaskDecomposer(config, bm)

        chart = decomposer._format_org_chart()
        assert "組織層級結構" in chart
        assert "manager" in chart
        assert "tech_lead" in chart
        assert "ui_designer" in chart

    def test_format_role_descriptions(self):
        """角色描述格式化應包含所有角色。"""
        from backend.company.budget import BudgetManager
        from backend.company.decomposer import TaskDecomposer

        config = BUILTIN_TEMPLATES["page_dev"]
        bm = BudgetManager(config.budget)
        decomposer = TaskDecomposer(config, bm)

        desc = decomposer._format_role_descriptions()
        for rt in config.roles:
            assert rt.value in desc


# ═══════════════════════════════════════════════════════════════
# 6.5. PromptConfig 自定義測試
# ═══════════════════════════════════════════════════════════════

class TestPromptConfig:
    """PromptConfig 自定義提示詞測試。"""

    def test_default_values_match_constants(self):
        """預設值應等於模組級常量。"""
        from backend.company.prompts import (
            DEVELOPER_EXECUTE,
            DEVELOPER_EXECUTE_SYSTEM,
            MANAGER_DECOMPOSE,
            MANAGER_DECOMPOSE_SYSTEM,
            MANAGER_FINAL_REVIEW,
            REVIEWER_REVIEW,
            REVIEWER_SYSTEM,
            ROLE_EXECUTE_PROMPTS,
            SYNTHESIZER_MERGE,
            SYNTHESIZER_SYSTEM,
            TEMPLATE_KEYWORDS,
        )

        pc = PromptConfig()
        assert pc.manager_decompose_system == MANAGER_DECOMPOSE_SYSTEM
        assert pc.manager_decompose == MANAGER_DECOMPOSE
        assert pc.manager_final_review == MANAGER_FINAL_REVIEW
        assert pc.developer_execute_system == DEVELOPER_EXECUTE_SYSTEM
        assert pc.developer_execute == DEVELOPER_EXECUTE
        assert pc.reviewer_system == REVIEWER_SYSTEM
        assert pc.reviewer_review == REVIEWER_REVIEW
        assert pc.synthesizer_system == SYNTHESIZER_SYSTEM
        assert pc.synthesizer_merge == SYNTHESIZER_MERGE
        assert pc.role_execute_prompts == ROLE_EXECUTE_PROMPTS
        assert pc.template_keywords == TEMPLATE_KEYWORDS

    def test_partial_customization(self):
        """部分自定義：只覆蓋部分欄位，其餘保持預設。"""
        custom_system = "你是一位敏捷教練"
        pc = PromptConfig(manager_decompose_system=custom_system)

        assert pc.manager_decompose_system == custom_system
        # 其他欄位應保持預設
        from backend.company.prompts import DEVELOPER_EXECUTE_SYSTEM
        assert pc.developer_execute_system == DEVELOPER_EXECUTE_SYSTEM

    def test_custom_role_execute_prompts(self):
        """自定義角色執行提示詞。"""
        custom_prompts = {
            "ui_designer": "自定義 UI 設計師提示詞",
            "backend_dev": "自定義後端開發者提示詞",
        }
        pc = PromptConfig(role_execute_prompts=custom_prompts)

        assert pc.role_execute_prompts["ui_designer"] == "自定義 UI 設計師提示詞"
        assert pc.role_execute_prompts["backend_dev"] == "自定義後端開發者提示詞"
        # 未覆蓋的角色不應存在
        assert "tester" not in pc.role_execute_prompts

    def test_custom_template_keywords(self):
        """自定義模板關鍵字映射。"""
        custom_template = [{"title": "自定義任務", "assignee": "developer", "depends_on": [], "complexity": "low"}]
        custom_keywords = {"自定義": custom_template}
        pc = PromptConfig(template_keywords=custom_keywords)

        assert "自定義" in pc.template_keywords
        assert pc.template_keywords["自定義"] == custom_template
        # 原有關鍵字不應存在
        assert "頁面" not in pc.template_keywords

    def test_custom_decompose_templates(self):
        """自定義分解模板。"""
        custom_templates = {
            "custom_flow": [
                {"title": "步驟1", "assignee": "developer", "depends_on": [], "complexity": "low"},
                {"title": "步驟2", "assignee": "reviewer", "depends_on": [0], "complexity": "medium"},
            ],
        }
        pc = PromptConfig(decompose_templates=custom_templates)

        assert "custom_flow" in pc.decompose_templates
        assert len(pc.decompose_templates["custom_flow"]) == 2
        assert "page_dev" not in pc.decompose_templates

    def test_via_company_config(self):
        """透過 CompanyConfig 注入自定義提示詞。"""
        custom_pc = PromptConfig(
            manager_decompose_system="自定義經理系統提示",
            developer_execute="自定義執行提示：{goal} / {role_name} / {title}",
        )
        config = CompanyConfig(
            name="自定義公司",
            prompt_config=custom_pc,
        )

        assert config.prompt_config.manager_decompose_system == "自定義經理系統提示"
        assert config.prompt_config.developer_execute == "自定義執行提示：{goal} / {role_name} / {title}"
        # 未覆蓋的欄位保持預設
        from backend.company.prompts import REVIEWER_SYSTEM
        assert config.prompt_config.reviewer_system == REVIEWER_SYSTEM

    def test_via_decomposer_constructor(self):
        """透過 TaskDecomposer 構造函數注入自定義提示詞。"""
        from backend.company.budget import BudgetManager

        custom_pc = PromptConfig(
            manager_decompose="自定義分解提示：{goal}",
        )
        config = BUILTIN_TEMPLATES["quick_task"]
        bm = BudgetManager(config.budget)
        decomposer = TaskDecomposer(config, bm, prompt_config=custom_pc)

        assert decomposer.prompt_config.manager_decompose == "自定義分解提示：{goal}"
        # config.prompt_config 不應被修改
        from backend.company.prompts import MANAGER_DECOMPOSE
        assert config.prompt_config.manager_decompose == MANAGER_DECOMPOSE

    def test_via_orchestrator_constructor(self):
        """透過 CompanyOrchestrator 構造函數注入自定義提示詞。"""
        from backend.company.orchestrator import CompanyOrchestrator

        custom_pc = PromptConfig(
            reviewer_review="自定義審查提示：{goal} / {title}",
        )
        config = BUILTIN_TEMPLATES["quick_task"]
        orchestrator = CompanyOrchestrator(config, prompt_config=custom_pc)

        assert orchestrator.prompt_config.reviewer_review == "自定義審查提示：{goal} / {title}"

    def test_full_customization_all_fields(self):
        """完全自定義所有欄位。"""
        pc = PromptConfig(
            manager_decompose_system="MDS",
            manager_decompose="MD",
            manager_final_review="MFR",
            developer_execute_system="DES",
            developer_execute="DE",
            role_execute_prompts={"dev": "custom"},
            reviewer_system="RS",
            reviewer_review="RR",
            synthesizer_system="SS",
            synthesizer_merge="SM",
            decompose_templates={"t1": []},
            template_keywords={"k1": []},
        )

        assert pc.manager_decompose_system == "MDS"
        assert pc.manager_decompose == "MD"
        assert pc.manager_final_review == "MFR"
        assert pc.developer_execute_system == "DES"
        assert pc.developer_execute == "DE"
        assert pc.role_execute_prompts == {"dev": "custom"}
        assert pc.reviewer_system == "RS"
        assert pc.reviewer_review == "RR"
        assert pc.synthesizer_system == "SS"
        assert pc.synthesizer_merge == "SM"
        assert pc.decompose_templates == {"t1": []}
        assert pc.template_keywords == {"k1": []}


# ═══════════════════════════════════════════════════════════════
# 7. EvoLoop 圖整合測試
# ═══════════════════════════════════════════════════════════════

class TestCompanyGraphIntegration:
    """公司模式在 EvoLoop 圖中的路由測試。"""

    def test_route_to_company_mode(self):
        """execution_strategy='company' 時路由到公司運行時。"""
        from backend.core.company_nodes import route_by_complexity

        state = {"execution_strategy": "company"}
        assert route_by_complexity(state) == "run_company"

    def test_route_to_standard_mode(self):
        """execution_strategy='simple' 時路由到單次生成。"""
        from backend.core.company_nodes import route_by_complexity

        state = {"execution_strategy": "simple"}
        assert route_by_complexity(state) == "generate_initial_answer"

    def test_route_default_is_standard(self):
        """未設定 execution_strategy 時預設為 auto（簡單 query 走單次生成）。"""
        from backend.core.company_nodes import route_by_complexity

        state = {"query": "你好"}
        assert route_by_complexity(state) == "generate_initial_answer"

    def test_run_company_with_mock(self, monkeypatch):
        """run_company 節點（模擬 LLM 呼叫）。

        成功時應回傳 current_answer（供 evaluate_answer 評估），
        而非直接設定 final_answer。
        """
        from backend.core.company_nodes import run_company

        monkeypatch.setenv("EVOL_MERGE_REVIEW_SYNTH", "false")

        state = {
            "query": "建立一個 API 文件",
            "company_template": "quick_task",
        }

        exec_responses = [
            "API 文件已完成",      # Developer 執行
            FAKE_REVIEW_APPROVED,    # Reviewer 審查
            "整合完成",            # Synthesizer 整合
            FAKE_FINAL_REVIEW,      # Manager 最終審查
        ]

        with patch.object(
            TaskDecomposer, "decompose",
            AsyncMock(return_value=FAKE_LOW_RESULT),
        ), patch(
            "backend.company.orchestrator.call_llm",
            side_effect=exec_responses,
        ):
            result = run_company(state)

        assert "current_answer" in result
        assert result["current_answer"] == "整合完成"
        assert "final_answer" not in result
        assert "company_result" in result
        assert "company_kanban" in result
        assert "company_budget" in result
        assert result["iteration"] == 0

    def test_run_company_error_handling(self):
        """run_company 錯誤處理（不崩潰）。

        失敗時應直接設定 final_answer（跳過評估迭代）。
        """
        from backend.company.orchestrator import CompanyOrchestrator
        from backend.core.company_nodes import run_company

        state = {
            "query": "測試",
            "company_template": "quick_task",
        }

        with patch.object(
            CompanyOrchestrator, "execute",
            AsyncMock(side_effect=RuntimeError("模擬錯誤")),
        ):
            result = run_company(state)

        assert "final_answer" in result
        assert "公司運行時執行失敗" in result["final_answer"]
        company_result = result.get("company_result", {})
        assert company_result.get("success") is False

    def test_should_evaluate_company_success(self):
        """公司執行成功時路由到 evaluate_answer（進入迭代迴圈）。"""
        from backend.core.company_nodes import should_evaluate_company

        state = {"company_result": {"success": True}}
        assert should_evaluate_company(state) == "evaluate_answer"

    def test_should_evaluate_company_failure(self):
        """公司執行失敗時路由到 archive_state（跳過迭代）。"""
        from backend.core.company_nodes import should_evaluate_company

        state = {"company_result": {"success": False}}
        assert should_evaluate_company(state) == "archive_state"

    def test_company_mode_passes_on_high_score(self, monkeypatch):
        """公司模式產出經評估分數達標時，直接輸出不迭代。"""
        from backend.core.graph import build_graph

        monkeypatch.setenv("EVOL_MERGE_REVIEW_SYNTH", "false")

        company_responses = [
            "高品質公司產出",     # Developer 執行
            FAKE_REVIEW_APPROVED,   # Reviewer 審查
            "整合完成",           # Synthesizer 整合
            FAKE_FINAL_REVIEW,     # Manager 最終審查
        ]

        eval_high = json.dumps(
            {"score": 9, "strengths": "完整", "weaknesses": ""},
            ensure_ascii=False,
        )

        store = MagicMock()
        store.search_similar.return_value = []

        with (
            patch.object(TaskDecomposer, "decompose", AsyncMock(return_value=FAKE_LOW_RESULT)),
            patch("backend.company.orchestrator.call_llm", side_effect=company_responses),
            patch("backend.core.nodes.call_llm", side_effect=[eval_high]),
            patch("backend.core.evaluation.call_llm", side_effect=[eval_high]),
            patch("backend.core.nodes._memory_store", store),
        ):
            result = build_graph().invoke({
                "query": "建立一個用戶管理系統",
                "execution_strategy": "company",
                "company_template": "quick_task",
            })

        assert result["final_answer"] == "整合完成"
        assert result["score"] == 9.0
        assert not result.get("reflections")
        assert result["company_result"]["success"] is True

    def test_company_mode_iterates_on_low_score(self):
        """公司模式產出經評估分數過低時，觸發反思迭代迴圈。"""
        from backend.core.graph import build_graph

        company_responses = [
            "公司產出（品質待改進）",   # Developer 執行
            FAKE_REVIEW_APPROVED,       # Reviewer 審查
            "整合完成",               # Synthesizer 整合
            FAKE_FINAL_REVIEW,         # Manager 最終審查
        ]

        eval_low = json.dumps(
            {"score": 5, "strengths": "方向正確", "weaknesses": "缺少細節"},
            ensure_ascii=False,
        )
        reflection = json.dumps(
            {"critique": "不夠完整", "suggestion": "補充更多細節"},
            ensure_ascii=False,
        )
        eval_high = json.dumps(
            {"score": 9, "strengths": "完整", "weaknesses": ""},
            ensure_ascii=False,
        )

        store = MagicMock()
        store.search_similar.return_value = []

        with (
            patch.object(TaskDecomposer, "decompose", AsyncMock(return_value=FAKE_LOW_RESULT)),
            patch("backend.company.orchestrator.call_llm", side_effect=company_responses),
            patch("backend.core.nodes.call_llm", side_effect=[reflection, "改進後的公司產出"]),
            patch("backend.core.evaluation.call_llm", side_effect=[eval_low, eval_high]),
            patch("backend.core.nodes._memory_store", store),
        ):
            result = build_graph().invoke({
                "query": "建立一個用戶管理系統",
                "execution_strategy": "company",
                "company_template": "quick_task",
            })

        assert result["final_answer"] == "改進後的公司產出"
        assert result["iteration"] == 1
        assert len(result["reflections"]) == 1
        assert result["company_result"]["success"] is True
        assert result["memory_saved"] is True

    def test_company_mode_failure_skips_iteration(self):
        """公司模式執行失敗時跳過評估迭代，直接存檔。"""
        from backend.company.orchestrator import CompanyOrchestrator
        from backend.core.graph import build_graph

        store = MagicMock()
        store.search_similar.return_value = []

        with (
            patch.object(CompanyOrchestrator, "execute", AsyncMock(side_effect=RuntimeError("LLM 不可用"))),
            patch("backend.core.nodes.call_llm") as mock_nodes_llm,
            patch("backend.core.nodes._memory_store", store),
        ):
            result = build_graph().invoke({
                "query": "測試",
                "execution_strategy": "company",
                "company_template": "quick_task",
            })

        assert "公司運行時執行失敗" in result["final_answer"]
        assert result["company_result"]["success"] is False
        # 標準節點 LLM 不應被呼叫（跳過評估迭代）
        mock_nodes_llm.assert_not_called()# ═══════════════════════════════════════════════════════════════
# 10. 事件系統測試
# ═══════════════════════════════════════════════════════════════

class TestEventSystem:
    """驗證 EventBus 與 CompanyEvent 的基礎功能。"""

    def test_event_bus_basic_emit(self):
        """測試基本事件發射與監聽。"""
        from backend.company.events import CompanyEvent, EventBus

        captured = []

        def listener(event, data):
            captured.append((event, data))

        bus = EventBus()
        bus.on(listener)
        bus.emit(CompanyEvent.WORK_ITEM_START, {"item_id": "abc"})

        assert len(captured) == 1
        assert captured[0][0] == CompanyEvent.WORK_ITEM_START
        assert captured[0][1]["item_id"] == "abc"

    def test_event_bus_multiple_listeners(self):
        """測試多個監聽器同時接收事件。"""
        from backend.company.events import CompanyEvent, EventBus

        results = []

        bus = EventBus()
        bus.on(lambda e, d: results.append(("A", e.value)))
        bus.on(lambda e, d: results.append(("B", e.value)))
        bus.emit(CompanyEvent.COMPANY_START, {})

        assert len(results) == 2
        assert ("A", "company_start") in results
        assert ("B", "company_start") in results

    def test_event_bus_off(self):
        """測試移除監聽器。"""
        from backend.company.events import CompanyEvent, EventBus

        results = []

        def listener_a(event, data):
            results.append("A")

        def listener_b(event, data):
            results.append("B")

        bus = EventBus()
        bus.on(listener_a)
        bus.on(listener_b)
        bus.off(listener_a)
        bus.emit(CompanyEvent.PHASE_CHANGE, {})

        assert results == ["B"]

    def test_event_bus_clear(self):
        """測試清除所有監聽器。"""
        from backend.company.events import CompanyEvent, EventBus

        results = []

        bus = EventBus()
        bus.on(lambda e, d: results.append("X"))
        bus.clear()
        bus.emit(CompanyEvent.WORK_ITEM_DONE, {})

        assert results == []

    def test_event_bus_listener_exception_ignored(self):
        """測試監聽器拋出異常不影響其他監聽器與主流程。"""
        from backend.company.events import CompanyEvent, EventBus

        results = []

        def bad_listener(event, data):
            raise RuntimeError("模擬監聽器異常")

        def good_listener(event, data):
            results.append("OK")

        bus = EventBus()
        bus.on(bad_listener)
        bus.on(good_listener)
        bus.emit(CompanyEvent.REVIEW_PASS, {})  # 不應拋出異常

        assert results == ["OK"]

    def test_event_bus_listener_count(self):
        """測試監聽器數量屬性。"""
        from backend.company.events import EventBus

        bus = EventBus()
        assert bus.listener_count == 0

        bus.on(lambda e, d: None)
        assert bus.listener_count == 1

        bus.on(lambda e, d: None)
        assert bus.listener_count == 2

    @pytest.mark.asyncio
    async def test_events_fired_during_execution(self, mock_llm_sequence):
        """測試完整執行流程中事件被正確發射。"""
        from unittest.mock import AsyncMock, patch

        from backend.company.events import CompanyEvent
        from backend.company.orchestrator import CompanyOrchestrator
        from backend.company.roles import STANDARD_ROLES
        from backend.company.state import CompanyConfig

        captured = []

        config = CompanyConfig(
            name="event_test",
            roles=STANDARD_ROLES,
            decompose_strategy="rule",
            max_review_rounds=1,
        )
        orch = CompanyOrchestrator(config=config)
        orch.events.on(lambda e, d: captured.append(e))

        with patch.object(
            orch.decomposer, "decompose",
            new_callable=AsyncMock,
        ) as mock_decompose, patch(
            "backend.company.orchestrator.call_llm",
            side_effect=mock_llm_sequence,
        ):
            from backend.company.decomposer import (
                DecompositionResult,
                DecompositionStrategy,
            )
            mock_decompose.return_value = DecompositionResult(
                goal="用 Python 寫一個 hello world 函數",
                subtasks=[{"title": "寫 hello world", "role": "developer", "complexity": "low"}],
                strategy=DecompositionStrategy.RULE,
            )
            await orch.execute("用 Python 寫一個 hello world 函數")

        # 至少應包含啟動和完成事件
        assert CompanyEvent.COMPANY_START in captured
        assert CompanyEvent.COMPANY_DONE in captured
        assert CompanyEvent.PHASE_CHANGE in captured

    def test_all_company_event_values(self):
        """測試 CompanyEvent 枚舉值的完整性。"""
        from backend.company.events import CompanyEvent

        expected = {
            "company_start", "company_done", "phase_change", "decompose_done",
            "work_item_start", "work_item_done", "work_item_error",
            "work_item_retry", "work_item_escalate",
            "tool_call", "tool_result",
            "review_pass", "review_rework", "review_force_done",
            "final_review_degraded",
            "budget_warning", "budget_degrade",
        }
        actual = {e.value for e in CompanyEvent}
        assert actual == expected


# ═══════════════════════════════════════════════════════════════
# 11. 增強錯誤處理測試
# ═══════════════════════════════════════════════════════════════

class TestErrorHandling:
    """驗證 RetryConfig、重試邏輯、角色升級。"""

    def test_retry_config_defaults(self):
        """測試 RetryConfig 預設值。"""
        from backend.company.state import RetryConfig

        cfg = RetryConfig()
        assert cfg.max_retries == 3
        assert cfg.retry_backoff_base == 1.0
        assert cfg.enable_escalation is True
        assert cfg.deadline_seconds == 300.0

    def test_retry_config_custom(self):
        """測試自訂 RetryConfig。"""
        from backend.company.state import RetryConfig

        cfg = RetryConfig(
            max_retries=5,
            retry_backoff_base=2.0,
            enable_escalation=False,
            deadline_seconds=60.0,
        )
        assert cfg.max_retries == 5
        assert cfg.retry_backoff_base == 2.0
        assert cfg.enable_escalation is False
        assert cfg.deadline_seconds == 60.0

    def test_retry_config_in_company_config(self):
        """測試 RetryConfig 整合到 CompanyConfig。"""
        from backend.company.state import CompanyConfig, RetryConfig

        custom_retry = RetryConfig(max_retries=2, enable_escalation=False)
        config = CompanyConfig(retry_config=custom_retry)
        assert config.retry_config.max_retries == 2
        assert config.retry_config.enable_escalation is False

    @pytest.mark.asyncio
    async def test_retry_on_llm_failure(self):
        """測試 LLM 失敗時觸發重試。"""
        from unittest.mock import AsyncMock, patch

        from backend.company.decomposer import (
            DecompositionResult,
            DecompositionStrategy,
        )
        from backend.company.events import CompanyEvent
        from backend.company.orchestrator import CompanyOrchestrator
        from backend.company.roles import STANDARD_ROLES
        from backend.company.state import CompanyConfig, RetryConfig

        captured = []
        fail_count = [0]

        def mock_llm(*args, **kwargs):
            fail_count[0] += 1
            if fail_count[0] <= 2:
                raise RuntimeError("模擬 LLM 失敗")
            return "成功"

        config = CompanyConfig(
            name="retry_test",
            roles=STANDARD_ROLES,
            decompose_strategy="rule",
            retry_config=RetryConfig(max_retries=2, retry_backoff_base=0.01, deadline_seconds=0),
            max_review_rounds=1,
        )
        orch = CompanyOrchestrator(config=config)
        orch.events.on(lambda e, d: captured.append(e))

        with patch.object(
            orch.decomposer, "decompose",
            new_callable=AsyncMock,
        ) as mock_decompose, patch(
            "backend.company.orchestrator.call_llm",
            side_effect=mock_llm,
        ):
            mock_decompose.return_value = DecompositionResult(
                goal="用 Python 寫一個 hello world 函數",
                subtasks=[{"title": "寫 hello world", "role": "developer", "complexity": "low"}],
                strategy=DecompositionStrategy.RULE,
            )
            await orch.execute("用 Python 寫一個 hello world 函數")

        # 應觸發重試事件
        retry_events = [e for e in captured if e == CompanyEvent.WORK_ITEM_RETRY]
        assert len(retry_events) >= 1

    @pytest.mark.asyncio
    async def test_escalation_on_final_failure(self, mock_llm_sequence):
        """測試所有重試耗盡後觸發角色升級（簡化版：只驗證事件發射）。"""
        from unittest.mock import patch

        from backend.company.events import CompanyEvent
        from backend.company.orchestrator import CompanyOrchestrator
        from backend.company.roles import STANDARD_ROLES
        from backend.company.state import CompanyConfig, RetryConfig, RoleType

        captured = []

        config = CompanyConfig(
            name="escalation_test",
            roles=STANDARD_ROLES,
            org_chart={
                RoleType.FRONTEND_LEAD: [RoleType.JS_DEV],
                RoleType.TECH_LEAD: [RoleType.FRONTEND_LEAD],
            },
            retry_config=RetryConfig(max_retries=1, retry_backoff_base=0.01, enable_escalation=True, deadline_seconds=0),
            max_review_rounds=1,
        )
        orch = CompanyOrchestrator(config=config)
        orch.events.on(lambda e, d: captured.append(e))

        # 手動建立一個工作項並觸發執行（模擬失敗 + 升級）
        from backend.company.state import BudgetTier, Priority, RoleType, WorkItem
        item = WorkItem(
            title="測試任務",
            description="測試升級",
            assignee=RoleType.JS_DEV,  # JS_DEV 的上級是 FRONTEND_LEAD
            tier=BudgetTier.ROUTINE,
            priority=Priority.MEDIUM,
        )
        orch.work_items._items[item.id] = item
        item.status = WorkItemStatus.READY

        def mock_llm_always_fail(*args, **kwargs):
            raise RuntimeError("模擬持續失敗")

        with patch("backend.company.orchestrator.call_llm", side_effect=mock_llm_always_fail):
            await orch._execute_single_item("test goal", item)

        # 應觸發升級事件
        escalate_events = [e for e in captured if e == CompanyEvent.WORK_ITEM_ESCALATE]
        assert len(escalate_events) >= 1

    @pytest.mark.asyncio
    async def test_no_escalation_when_disabled(self):
        """測試停用升級時不觸發升級事件（簡化版）。"""
        from unittest.mock import patch

        from backend.company.events import CompanyEvent
        from backend.company.orchestrator import CompanyOrchestrator
        from backend.company.roles import STANDARD_ROLES
        from backend.company.state import (
            BudgetTier,
            CompanyConfig,
            Priority,
            RetryConfig,
            RoleType,
            WorkItem,
            WorkItemStatus,
        )

        captured = []

        config = CompanyConfig(
            name="no_escalation_test",
            roles=STANDARD_ROLES,
            org_chart={
                RoleType.FRONTEND_LEAD: [RoleType.JS_DEV],
            },
            retry_config=RetryConfig(max_retries=1, retry_backoff_base=0.01, enable_escalation=False, deadline_seconds=0),
        )
        orch = CompanyOrchestrator(config=config)
        orch.events.on(lambda e, d: captured.append(e))

        item = WorkItem(
            title="測試任務",
            description="測試無升級",
            assignee=RoleType.JS_DEV,
            tier=BudgetTier.ROUTINE,
            priority=Priority.MEDIUM,
        )
        orch.work_items._items[item.id] = item
        item.status = WorkItemStatus.READY

        def mock_llm_always_fail(*args, **kwargs):
            raise RuntimeError("模擬持續失敗")

        with patch("backend.company.orchestrator.call_llm", side_effect=mock_llm_always_fail):
            await orch._execute_single_item("test goal", item)

        escalate_events = [e for e in captured if e == CompanyEvent.WORK_ITEM_ESCALATE]
        assert len(escalate_events) == 0


# ═══════════════════════════════════════════════════════════════
# 12. 檢查點測試
# ═══════════════════════════════════════════════════════════════

class TestCheckpointing:
    """驗證 to_checkpoint / from_checkpoint 序列化與恢復。"""

    @pytest.mark.asyncio
    async def test_to_checkpoint_after_execution(self, mock_llm_sequence):
        """測試執行後可產生檢查點。"""
        from unittest.mock import AsyncMock, patch

        from backend.company.decomposer import (
            DecompositionResult,
            DecompositionStrategy,
        )
        from backend.company.orchestrator import CompanyOrchestrator
        from backend.company.roles import STANDARD_ROLES
        from backend.company.state import CompanyConfig

        config = CompanyConfig(
            name="checkpoint_test",
            roles=STANDARD_ROLES,
            decompose_strategy="rule",
            max_review_rounds=1,
        )
        orch = CompanyOrchestrator(config=config)

        with patch.object(
            orch.decomposer, "decompose",
            new_callable=AsyncMock,
        ) as mock_decompose, patch(
            "backend.company.orchestrator.call_llm",
            side_effect=mock_llm_sequence,
        ):
            mock_decompose.return_value = DecompositionResult(
                goal="用 Python 寫一個 hello world 函數",
                subtasks=[{"title": "寫 hello world", "role": "developer", "complexity": "low"}],
                strategy=DecompositionStrategy.RULE,
            )
            await orch.execute("用 Python 寫一個 hello world 函數")

        checkpoint = orch.to_checkpoint(goal="用 Python 寫一個 hello world 函數")

        assert "goal" in checkpoint
        assert checkpoint["goal"] == "用 Python 寫一個 hello world 函數"
        assert checkpoint["config_name"] == "checkpoint_test"
        assert "timestamp" in checkpoint
        assert "work_items" in checkpoint
        assert "budget" in checkpoint
        assert "run_log" in checkpoint
        assert len(checkpoint["work_items"]) > 0

    @pytest.mark.asyncio
    async def test_work_item_serialization_in_checkpoint(self, mock_llm_sequence):
        """測試檢查點中工作項欄位的完整性。"""
        from unittest.mock import AsyncMock, patch

        from backend.company.decomposer import (
            DecompositionResult,
            DecompositionStrategy,
        )
        from backend.company.orchestrator import CompanyOrchestrator
        from backend.company.roles import STANDARD_ROLES
        from backend.company.state import CompanyConfig

        config = CompanyConfig(
            name="serial_test",
            roles=STANDARD_ROLES,
            decompose_strategy="rule",
            max_review_rounds=1,
        )
        orch = CompanyOrchestrator(config=config)

        with patch.object(
            orch.decomposer, "decompose",
            new_callable=AsyncMock,
        ) as mock_decompose, patch(
            "backend.company.orchestrator.call_llm",
            side_effect=mock_llm_sequence,
        ):
            mock_decompose.return_value = DecompositionResult(
                goal="用 Python 寫一個 hello world 函數",
                subtasks=[{"title": "寫 hello world", "role": "developer", "complexity": "low"}],
                strategy=DecompositionStrategy.RULE,
            )
            await orch.execute("用 Python 寫一個 hello world 函數")

        checkpoint = orch.to_checkpoint(goal="test")
        item = checkpoint["work_items"][0]

        assert "id" in item
        assert "title" in item
        assert "description" in item
        assert "assignee" in item
        assert "status" in item
        assert "tier" in item
        assert "priority" in item
        assert "dependencies" in item
        assert "artifacts" in item
        assert "actual_cost" in item
        assert "review_count" in item
        assert "created_by" in item

    @pytest.mark.asyncio
    async def test_from_checkpoint_restores_state(self, mock_llm_sequence):
        """測試 from_checkpoint 恢復完整狀態。"""
        from unittest.mock import AsyncMock, patch

        from backend.company.decomposer import (
            DecompositionResult,
            DecompositionStrategy,
        )
        from backend.company.orchestrator import CompanyOrchestrator
        from backend.company.roles import STANDARD_ROLES
        from backend.company.state import CompanyConfig

        config = CompanyConfig(
            name="restore_test",
            roles=STANDARD_ROLES,
            decompose_strategy="rule",
            max_review_rounds=1,
        )

        # 第一次執行
        orch1 = CompanyOrchestrator(config=config)
        with patch.object(
            orch1.decomposer, "decompose",
            new_callable=AsyncMock,
        ) as mock_decompose, patch(
            "backend.company.orchestrator.call_llm",
            side_effect=mock_llm_sequence,
        ):
            mock_decompose.return_value = DecompositionResult(
                goal="用 Python 寫一個 hello world 函數",
                subtasks=[{"title": "寫 hello world", "role": "developer", "complexity": "low"}],
                strategy=DecompositionStrategy.RULE,
            )
            await orch1.execute("用 Python 寫一個 hello world 函數")
        checkpoint = orch1.to_checkpoint(goal="用 Python 寫一個 hello world 函數")

        # 從檢查點恢復
        orch2 = CompanyOrchestrator.from_checkpoint(checkpoint, config=config)
        assert orch2.work_items.get_stats() == orch1.work_items.get_stats()
        assert orch2.budget.task_spent == orch1.budget.task_spent

    def test_to_checkpoint_before_execution(self):
        """測試執行前檢查點為空。"""
        from backend.company.orchestrator import CompanyOrchestrator

        orch = CompanyOrchestrator()
        checkpoint = orch.to_checkpoint(goal="test")

        assert checkpoint["goal"] == "test"
        assert checkpoint["work_items"] == []


# ═══════════════════════════════════════════════════════════════
# 13. 優先級 + 工作池測試
# ═══════════════════════════════════════════════════════════════

class TestPriorityAndWorkerPool:
    """驗證 Priority 枚舉、優先級排序、Semaphore 工作池。"""

    def test_priority_enum_values(self):
        """測試 Priority 枚舉值。"""
        from backend.company.state import Priority

        assert Priority.CRITICAL.value == 0
        assert Priority.HIGH.value == 1
        assert Priority.MEDIUM.value == 2
        assert Priority.LOW.value == 3

    def test_priority_ordering(self):
        """測試優先級排序（數值越小越優先）。"""
        from backend.company.state import Priority

        priorities = [Priority.LOW, Priority.CRITICAL, Priority.MEDIUM, Priority.HIGH]
        sorted_priorities = sorted(priorities, key=lambda p: p.value)

        assert sorted_priorities == [
            Priority.CRITICAL,
            Priority.HIGH,
            Priority.MEDIUM,
            Priority.LOW,
        ]

    def test_work_item_default_priority(self):
        """測試工作項預設優先級為 MEDIUM。"""
        from backend.company.state import Priority, WorkItem

        item = WorkItem(title="測試任務")
        assert item.priority == Priority.MEDIUM

    def test_work_item_custom_priority(self):
        """測試工作項可自訂優先級。"""
        from backend.company.state import Priority, WorkItem

        item = WorkItem(title="關鍵任務", priority=Priority.CRITICAL)
        assert item.priority == Priority.CRITICAL

    def test_get_ready_items_sorted_by_priority(self):
        """測試 get_ready_items 按優先級排序。"""
        from backend.company.state import Priority, WorkItemStatus
        from backend.company.work_item import WorkItemManager

        mgr = WorkItemManager()

        low = mgr.create("低優先級任務", priority=Priority.LOW)
        high = mgr.create("高優先級任務", priority=Priority.HIGH)
        crit = mgr.create("關鍵任務", priority=Priority.CRITICAL)
        med = mgr.create("中優先級任務", priority=Priority.MEDIUM)

        # 全部設為 READY
        for item in [low, high, crit, med]:
            item.status = WorkItemStatus.READY

        ready = mgr.get_ready_items()
        priorities = [item.priority for item in ready]

        assert priorities == [Priority.CRITICAL, Priority.HIGH, Priority.MEDIUM, Priority.LOW]

    def test_priority_in_create_method(self):
        """測試 WorkItemManager.create() 支援 priority 參數。"""
        from backend.company.state import Priority
        from backend.company.work_item import WorkItemManager

        mgr = WorkItemManager()
        item = mgr.create("優先任務", priority=Priority.HIGH)

        assert item.priority == Priority.HIGH

    def test_semaphore_limits_parallel_workers(self):
        """測試 Semaphore 限制並行工作數。"""
        from backend.company.orchestrator import CompanyOrchestrator
        from backend.company.roles import STANDARD_ROLES
        from backend.company.state import CompanyConfig

        config = CompanyConfig(
            name="semaphore_test",
            roles=STANDARD_ROLES,
            max_parallel_workers=2,
        )
        orch = CompanyOrchestrator(config=config)

        # 驗證 Semaphore 已建立
        assert orch._worker_semaphore is not None
        # 驗證初始值等於配置
        assert orch._worker_semaphore._value == 2

    def test_max_parallel_workers_default(self):
        """測試預設 max_parallel_workers 值。"""
        from backend.company.state import CompanyConfig

        config = CompanyConfig()
        assert config.max_parallel_workers == 4  # 預設值