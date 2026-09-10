"""輸出長度守門節點：超過依複雜度解析出的上限時，丢回反思閉環重寫。

測試走節點公共接口與圖級 invoke，不碰內部協作者實作細節。
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from backend.core import nodes
from backend.core.graph import build_graph


@pytest.fixture(autouse=True)
def _enable_cost_speed(monkeypatch):
    monkeypatch.delenv("EVOL_COST_SPEED_ENABLED", raising=False)


class FakeLLM:
    """依序回傳預設腳本的模擬 LLM。"""

    def __init__(self, responses: list[str]):
        self.responses = responses
        self.prompts: list[str] = []

    def __call__(self, prompt, system=None, model=None, **kwargs):
        self.prompts.append(prompt)
        if len(self.prompts) > len(self.responses):
            raise AssertionError(f"LLM 被呼叫超過預期的 {len(self.responses)} 次")
        return self.responses[len(self.prompts) - 1]


def _evaluation(score: float, weaknesses: str = "") -> str:
    return json.dumps(
        {"score": score, "strengths": "ok", "weaknesses": weaknesses},
        ensure_ascii=False,
    )


def _reflection() -> str:
    return json.dumps(
        {"critique": "缺少具體步驟", "suggestion": "補充操作細節"},
        ensure_ascii=False,
    )


def _answer(chars: int) -> str:
    """指定長度的回答（用於長度斷言）。"""
    return "說" * chars


def _run_graph(fake: FakeLLM, query: str, state: dict | None = None) -> dict:
    store = MagicMock()
    store.search_similar.return_value = []
    with (
        patch("backend.core.nodes.call_llm", side_effect=fake),
        patch("backend.core.evaluation.call_llm", side_effect=fake),
        patch("backend.core.nodes._memory_store", store),
    ):
        payload = {"query": query}
        payload.update(state or {})
        return build_graph().invoke(payload)


class TestLengthGatePassThrough:
    def test_within_limit_changes_nothing(self):
        state = {
            "query": "什麼是 Python？",
            "task_complexity": "simple",
            "current_answer": "Python 是一種直譯式語言。",
        }
        with patch("backend.core.nodes.call_llm") as llm:
            update = nodes.enforce_output_length(state)

        assert "current_answer" not in update
        assert not update.get("length_directive")
        llm.assert_not_called()


class TestLengthGateRewriteLoop:
    def test_over_limit_answer_is_sent_back_through_reflection_loop(self):
        """simple 任務上限 800 字：超長初始回答必須經反思改進收斂後才交付。"""
        long_answer = "說" * 900
        concise = "Python 是直譯式語言。"
        fake = FakeLLM([
            long_answer,      # generate_initial_answer
            _reflection(),    # reflect
            concise,          # improve_answer
            _evaluation(9),   # evaluate_answer
        ])
        result = _run_graph(fake, "什麼是 Python？")

        assert result["length_rewrites"] == 1
        assert result["final_answer"] == concise
        assert len(result["reflections"]) == 1


class TestLengthDirectiveReachesPrompts:
    def test_reflect_and_improve_prompts_carry_length_requirement(self):
        """丢回閉環後，反思與改進都必須看見長度硬性要求，否則迭代不會收斂。"""
        long_answer = "說" * 900
        fake = FakeLLM([
            long_answer,      # generate_initial_answer
            _reflection(),    # reflect
            "Python 是直譯式語言。",  # improve_answer
            _evaluation(9),   # evaluate_answer
        ])
        _run_graph(fake, "什麼是 Python？")

        reflect_prompt = fake.prompts[1]
        improve_prompt = fake.prompts[2]
        assert "上限 800 字元" in reflect_prompt
        assert "超出 100 字元" in reflect_prompt
        assert "上限 800 字元" in improve_prompt

    def test_no_length_requirement_when_answer_within_limit(self):
        fake = FakeLLM([
            "初始回答（品質不佳）",
            _evaluation(5, "不完整"),
            _reflection(),
            "改進後的回答",
            _evaluation(9),
        ])
        _run_graph(fake, "測試問題")

        # 此路徑順序：生成 → 評估 → 反思 → 改進 → 評估
        assert "輸出長度硬性要求" not in fake.prompts[2]
        assert "輸出長度硬性要求" not in fake.prompts[3]


class TestLengthRewriteBudget:
    def test_budget_exhausted_delivers_shortest_and_warns(self):
        """最多丢回 2 次；仍超標則交付歷次最短的一版並記警告，不得無限循環。"""
        fake = FakeLLM([
            _answer(1000),      # generate_initial_answer
            _reflection(),      # reflect（第 1 次重寫）
            _answer(1500),      # improve_answer：更長，屬退步
            _reflection(),      # reflect（第 2 次重寫）
            _answer(1100),      # improve_answer：仍超標
            _evaluation(9),     # evaluate_answer：預算用盡後才進評估
        ])
        result = _run_graph(fake, "什麼是 Python？")

        assert result["length_rewrites"] == 2
        # 800 上限：保留三者中最短的初始版，而非最後一版
        assert result["final_answer"] == _answer(1000)
        assert result.get("length_warnings")
        assert "800" in result["length_warnings"][0]
        # 沒有第三次重寫（generate/reflect/improve/reflect/improve/evaluate）
        assert len(fake.prompts) == 6


class TestDeliveryLengthGate:
    def test_downgraded_initial_answer_is_still_gated(self):
        """改進後回答為空 → decide_final_answer 降級改用超長的初始回答；
        交付端守門必須再拦一道，並把實際要交付的那份丟回閉環壓縮。"""
        long_initial = "說" * 1200
        concise = "Python 是直譯式語言。"
        fake = FakeLLM([
            long_initial,      # generate_initial_answer
            _reflection(),     # reflect（評估前守門第 1 次丢回）
            "",                # improve_answer：產出為空
            _evaluation(9),    # evaluate_answer
            _reflection(),     # reflect（交付端守門第 2 次丢回）
            concise,           # improve_answer
            _evaluation(9),    # evaluate_answer
        ])
        result = _run_graph(fake, "什麼是 Python？")

        assert result["final_answer"] == concise
        assert len(result["final_answer"]) <= 800
        assert result["length_rewrites"] == 2
        # 第二次丢回時，閉環拿到的原始回答是被降級的超長版本，而非空字串
        assert long_initial in fake.prompts[4]


class TestLengthGateFailOpen:
    def test_none_answer_does_not_become_a_crash(self):
        update = nodes.enforce_output_length({
            "query": "什麼是 Python？",
            "task_complexity": "simple",
            "current_answer": None,
        })
        assert update.get("length_directive", "") == ""

    def test_unrecognised_complexity_label_falls_back_to_default_limit(self):
        update = nodes.enforce_output_length({
            "query": "什麼是 Python？",
            "task_complexity": "外星標籤",
            "current_answer": "說" * 4001,
        })
        assert update["max_output_chars"] == 4000
        assert "上限 4000 字元" in update["length_directive"]

    def test_delivery_gate_tolerates_missing_final_answer(self):
        update = nodes.enforce_final_length({
            "query": "什麼是 Python？",
            "task_complexity": "simple",
            "current_answer": "說" * 900,
        })
        assert update.get("length_directive", "") == ""


class TestDeliveryGateForLoopsOutsideTheGraph:
    """`/chat/stream`、`_company_stream`、task_manager 的反思迴圈是圖外手抄的，
    改圖拓撲不會生效，必須各自接上同一個守門節點。"""

    def _sse_lines(self, client, query: str) -> list[str]:
        lines: list[str] = []
        with client.stream("POST", "/chat/stream", json={"query": query}) as resp:
            for line in resp.iter_lines():
                if line:
                    lines.append(line)
        return lines

    def test_stream_endpoint_rewrites_over_long_answer(self, monkeypatch):
        from fastapi.testclient import TestClient

        from backend.main import app

        concise = "Python 是直譯式語言。"
        monkeypatch.setattr(
            "backend.main.call_llm_stream",
            lambda prompt, system=None, **kw: iter(["說" * 900]),
        )
        fake = FakeLLM([
            _evaluation(9),     # evaluate_answer
            _reflection(),      # reflect（長度预算内的額外一輪）
            concise,            # improve_answer
            _evaluation(9),     # evaluate_answer
        ])
        store = MagicMock()
        store.search_similar.return_value = []
        with (
            patch("backend.core.nodes.call_llm", side_effect=fake),
            patch("backend.core.evaluation.call_llm", side_effect=fake),
            patch("backend.core.nodes._memory_store", store),
            TestClient(app) as client,
        ):
            lines = self._sse_lines(client, "什麼是 Python？")

        payloads = [
            json.loads(ln.split("data:", 1)[1].strip())
            for ln in lines
            if ln.startswith("data:") and '"answer"' in ln
        ]
        assert payloads, f"SSE 未送出答案事件：{lines}"
        assert payloads[-1]["answer"] == concise
        assert payloads[-1]["iteration"] == 1


class TestCompanyStreamLengthGate:
    def test_over_long_company_output_is_rewritten(self, monkeypatch):
        """公司產出同樣要過守門：它經 _company_stream 的手抄迴圈，而非 LangGraph。"""
        from fastapi.testclient import TestClient

        from backend.company.orchestrator import CompanyOrchestrator
        from backend.main import app

        concise = "精簡後的架構方案：三層服務。"
        long_output = "說" * 4500  # complex 任務上限 4000

        async def _fake_execute(self, query):
            return {"final_output": long_output, "success": True, "stats": {}}

        monkeypatch.setattr(CompanyOrchestrator, "execute", _fake_execute)
        fake = FakeLLM([
            _evaluation(9),   # evaluate_answer
            _reflection(),    # reflect（長度指令驅動的額外一輪）
            concise,          # improve_answer
            _evaluation(9),   # evaluate_answer
        ])
        store = MagicMock()
        store.search_similar.return_value = []
        lines: list[str] = []
        with (
            patch("backend.core.nodes.call_llm", side_effect=fake),
            patch("backend.core.evaluation.call_llm", side_effect=fake),
            patch("backend.core.nodes._memory_store", store),
            TestClient(app) as client,client.stream(
            "POST", "/chat/stream",
            json={
                "query": "請設計並實現一個完整的微服務系統架構",
                "execution_strategy": "company",
            },
        ) as resp
        ):
            for line in resp.iter_lines():
                if line:
                    lines.append(line)

        payloads = [
            json.loads(ln.split("data:", 1)[1].strip())
            for ln in lines
            if ln.startswith("data:") and '"answer"' in ln
        ]
        assert payloads, f"SSE 未送出 done 事件：{lines}"
        assert payloads[-1]["answer"] == concise
        assert payloads[-1]["iteration"] == 1


class TestBackgroundTaskLengthGate:
    @pytest.mark.asyncio
    async def test_task_reflection_loop_rewrites_over_long_answer(self):
        """`POST /tasks` 的背景反思迴圈同樣是圖外手抄，需接上同一守門節點。"""
        from backend.services.task_manager import TaskManager, TaskRecord

        concise = "Python 是直譯式語言。"
        fake = FakeLLM([
            _evaluation(9),   # evaluate_answer
            _reflection(),    # reflect（長度指令驅動的額外一輪）
            concise,          # improve_answer
            _evaluation(9),   # evaluate_answer
        ])
        store = MagicMock()
        store.search_similar.return_value = []
        record = TaskRecord("task-len-1", "什麼是 Python？", "simple", "quick_task")
        long_answer = "說" * 900
        state = {
            "query": "什麼是 Python？",
            "session_id": record.task_id,
            "task_complexity": "simple",
            "initial_answer": long_answer,
            "current_answer": long_answer,
            "iteration": 0,
        }
        with (
            patch("backend.core.nodes.call_llm", side_effect=fake),
            patch("backend.core.evaluation.call_llm", side_effect=fake),
            patch("backend.core.nodes._memory_store", store),
        ):
            await TaskManager()._run_reflection_loop(record, state, MagicMock())

        assert state["current_answer"] == concise
        assert state["length_rewrites"] == 1
        assert state["iteration"] == 1


class TestLimitFollowsComplexity:
    @pytest.mark.parametrize(
        "complexity,limit",
        [("simple", 800), ("medium", 2000), ("complex", 4000)],
    )
    def test_gate_holds_each_complexity_to_its_own_limit(self, complexity, limit):
        state = {
            "query": "測試問題",
            "task_complexity": complexity,
            "current_answer": "說" * (limit + 1),
        }
        update = nodes.enforce_output_length(state)

        assert update["max_output_chars"] == limit
        assert f"上限 {limit} 字元" in update["length_directive"]
