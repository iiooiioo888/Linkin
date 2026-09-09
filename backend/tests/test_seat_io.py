"""席位 I/O 監察軌跡測試。

驗證：
1. seat_io 倉的寫入、過濾、全文截斷、跨重啟（磁盤回退）
2. run 上下文綁定（ContextVar）讓 orchestrator 之外的席位也能歸屬正確 run
3. 公司執行真的把「投遞給模型的 prompt 全文」落了盤（這是監察頁的資料源）
4. 任務快照的事件截斷可調（events_limit）
5. /monitor/raho/feed 的輕量投影不夾帶正文
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.company.decomposer import DecompositionResult, DecompositionStrategy
from backend.company.roles import BUILTIN_TEMPLATES
from backend.company.seat_io import (
    TEXT_LIMIT,
    STORE,
    bind_run,
    record_seat_io,
    seat_log_path,
    unbind_run,
)


@pytest.fixture(autouse=True)
def _isolate_seat_io():
    """每筆測試清空環形緩衝；JSONL 目錄由 conftest 隔離至暫存。"""
    STORE.clear()
    yield
    STORE.clear()


FAKE_EXECUTE = "這是實作結果：完成了功能開發。"
FAKE_REVIEW_OK = json.dumps(
    {"approved": True, "score": 8, "strengths": "完整", "weaknesses": "", "feedback": ""}
)
FAKE_SYNTH = "整合結果：需求分析完成，功能實作完成。"
FAKE_FINAL = json.dumps(
    {
        "approved": True,
        "summary": "專案成功完成",
        "key_decisions": [],
        "recommendations": [],
        "lessons_learned": "",
    }
)
FAKE_PLAN = DecompositionResult(
    goal="",
    strategy=DecompositionStrategy.LLM,
    subtasks=[{"title": "任務", "assignee": "developer", "depends_on": [], "complexity": "medium"}],
    execution_plan="單一任務",
)


# ═══════════════════════════════════════════════════════════════
# 1. 倉庫本身
# ═══════════════════════════════════════════════════════════════


class TestSeatIOStore:
    def test_record_returns_normalized_row(self):
        row = record_seat_io(
            {
                "run_id": "r1",
                "task_id": "t1",
                "role": "developer",
                "kind": "execute",
                "prompt": "P",
                "system": "S",
                "response": "R",
                "context_sources": [{"kind": "tools", "label": "工具白名單", "text": "abc"}],
            }
        )
        assert row is not None
        assert row["run_id"] == "r1"
        assert row["prompt_length"] == 1
        assert row["truncated"] is False
        assert row["context_sources"][0]["kind"] == "tools"
        assert row["context_sources"][0]["chars"] == 3

    def test_list_filters_and_orders_new_first(self):
        record_seat_io({"run_id": "a", "role": "developer", "prompt": "1", "response": "x"})
        record_seat_io({"run_id": "b", "role": "reviewer", "prompt": "2", "response": "y"})
        assert [r["run_id"] for r in STORE.list()] == ["b", "a"]
        assert [r["run_id"] for r in STORE.list(role="reviewer")] == ["b"]
        assert [r["run_id"] for r in STORE.list(run_id="a")] == ["a"]

    def test_overlong_text_is_clipped_and_flagged(self):
        row = record_seat_io(
            {"run_id": "r", "prompt": "x" * (TEXT_LIMIT + 500), "response": "y", "system": "s"}
        )
        assert row["truncated"] is True
        assert len(row["prompt"]) == TEXT_LIMIT
        # 截斷不丟失原始長度資訊
        assert row["prompt_length"] == TEXT_LIMIT + 500

    def test_persisted_and_readable_from_disk_after_buffer_clear(self):
        row = record_seat_io({"run_id": "r9", "role": "developer", "prompt": "P", "response": "R"})
        path = seat_log_path("r9")
        assert path.exists()
        STORE.clear()
        assert STORE.list(run_id="r9") == []
        # 環形緩衝清空後仍能按 io_id 從磁盤取回（進程重啟可查）
        fetched = STORE.get(row["io_id"])
        assert fetched is not None
        assert fetched["prompt"] == "P"
        assert STORE.load_run("r9")[0]["io_id"] == row["io_id"]

    def test_run_log_and_seat_log_are_separate_files(self):
        """席位正文不得混入 run_*.jsonl，否則 agent_monitor 會把它塞進各席位事件流。"""
        record_seat_io({"run_id": "r8", "role": "developer", "prompt": "P", "response": "R"})
        assert seat_log_path("r8").exists()
        from backend.company.run_log import run_log_path

        assert not run_log_path("r8").exists()


class TestRunContextBinding:
    def test_bind_run_supplies_missing_ids(self):
        token = bind_run("run-x", "task-x")
        try:
            row = record_seat_io({"role": "developer", "prompt": "P", "response": "R"})
        finally:
            unbind_run(token)
        assert row["run_id"] == "run-x"
        assert row["task_id"] == "task-x"

    def test_explicit_ids_win_over_context(self):
        token = bind_run("run-x", "task-x")
        try:
            row = record_seat_io({"run_id": "explicit", "role": "developer", "prompt": "P", "response": "R"})
        finally:
            unbind_run(token)
        assert row["run_id"] == "explicit"
        assert row["task_id"] == "task-x"


# ═══════════════════════════════════════════════════════════════
# 2. 公司執行真的落下了投遞全文
# ═══════════════════════════════════════════════════════════════


class TestCompanyCapturesSeatIO:
    @pytest.mark.asyncio
    async def test_full_run_records_prompt_and_response(self):
        from backend.company.orchestrator import CompanyOrchestrator

        orchestrator = CompanyOrchestrator(BUILTIN_TEMPLATES["quick_task"])
        orchestrator.task_id = "task-42"

        with patch.object(
            orchestrator.decomposer, "decompose", new_callable=AsyncMock, return_value=FAKE_PLAN
        ), patch(
            "backend.company.orchestrator.call_llm",
            side_effect=[FAKE_EXECUTE, FAKE_REVIEW_OK, FAKE_SYNTH, FAKE_FINAL],
        ):
            result = await orchestrator.execute("開發一個小功能")

        run_id = result["run_id"]
        rows = STORE.list(run_id=run_id)
        assert rows, "公司執行未落下任何席位投遞軌跡"

        kinds = {r["kind"] for r in rows}
        assert "execute" in kinds
        assert "review" in kinds

        exec_rows = [r for r in rows if r["kind"] == "execute"]
        assert exec_rows[0]["response"] == FAKE_EXECUTE
        # 這一條是本次改造的核心：過去 prompt 組裝完即丟，無從監察
        assert exec_rows[0]["prompt"]
        assert exec_rows[0]["system"]
        assert exec_rows[0]["task_id"] == "task-42"
        assert exec_rows[0]["item_id"]
        assert exec_rows[0]["role"] == "developer"
        assert exec_rows[0]["layer"] == 2
        assert exec_rows[0]["context_sources"], "輸入來源分解未記錄"

        review_rows = [r for r in rows if r["kind"] == "review"]
        assert review_rows[0]["role"] == "reviewer"
        assert review_rows[0]["response"] == FAKE_REVIEW_OK

        # 全部投遞都可用 io_id 取回全文
        for row in rows:
            assert STORE.get(row["io_id"])["io_id"] == row["io_id"]

    @pytest.mark.asyncio
    async def test_llm_failure_still_records_invocation(self):
        """失敗投遞也要留痕，否則監察頁看不出角色是在哪一步燒掉的。"""
        from backend.company.orchestrator import CompanyOrchestrator

        orchestrator = CompanyOrchestrator(BUILTIN_TEMPLATES["quick_task"])

        with patch.object(
            orchestrator.decomposer, "decompose", new_callable=AsyncMock, return_value=FAKE_PLAN
        ), patch(
            "backend.company.orchestrator.call_llm",
            side_effect=RuntimeError("上游 503"),
        ):
            await orchestrator.execute("才會失敗的任務")

        failed = [r for r in STORE.list() if r["degraded"]]
        assert failed
        assert "上游 503" in failed[0]["error"]
        assert failed[0]["response"] == ""

    def test_inspector_records_under_bound_run(self):
        """L1 憲兵在 orchestrator 之外，靠 run 上下文綁定歸屬。"""
        from backend.company.raho.inspector import InspectorGate

        token = bind_run("run-inspect", "task-inspect")
        try:
            gate = InspectorGate(llm=lambda _prompt: "[PASS] 規格與產出一致")
            gate._llm_inspect({"node_id": "N1", "title": "組裝"}, "L2 產出內容", None)
        finally:
            unbind_run(token)

        rows = STORE.list(run_id="run-inspect")
        assert len(rows) == 1
        assert rows[0]["kind"] == "inspect"
        assert rows[0]["lane"] == "inspect"
        assert rows[0]["role"] == "constitutional_inspector"
        assert rows[0]["item_id"] == "N1"
        assert rows[0]["task_id"] == "task-inspect"
        assert "L2 產出內容" in rows[0]["prompt"]


# ═══════════════════════════════════════════════════════════════
# 3. 任務快照事件截斷
# ═══════════════════════════════════════════════════════════════


class TestTaskEventsLimit:
    def _record(self):
        from backend.services.task_manager import TaskRecord

        record = TaskRecord("t1", "q", "company", "quick_task")
        record.events = [{"ts": i, "event": f"e{i}", "data": {}} for i in range(30)]
        return record

    def test_default_keeps_events_within_limit(self):
        data = self._record().to_dict()
        assert len(data["events"]) == 30
        assert data["events_total"] == 30
        assert data["events_truncated"] is False

    def test_default_caps_at_fifty(self):
        from backend.services.task_manager import TaskRecord

        record = TaskRecord("t2", "q", "company", "quick_task")
        record.events = [{"ts": i, "event": f"e{i}", "data": {}} for i in range(80)]
        data = record.to_dict()
        assert len(data["events"]) == 50
        assert data["events"][0]["event"] == "e30"
        assert data["events_total"] == 80
        assert data["events_truncated"] is True

    def test_limit_slices_and_reports_truncation(self):
        data = self._record().to_dict(events_limit=10)
        assert len(data["events"]) == 10
        assert data["events"][0]["event"] == "e20"
        assert data["events_total"] == 30
        assert data["events_truncated"] is True

    def test_zero_or_none_returns_all(self):
        assert len(self._record().to_dict(events_limit=0)["events"]) == 30
        assert len(self._record().to_dict(events_limit=None)["events"]) == 30

    def test_snapshot_keeps_all_events(self):
        snap = self._record().to_snapshot()
        assert len(snap["events"]) == 30
        assert snap["events_truncated"] is False


# ═══════════════════════════════════════════════════════════════
# 4. 餵給端點
# ═══════════════════════════════════════════════════════════════


class TestFeedEndpoint:
    def test_light_projection_hides_bodies(self):
        from backend.main import app

        record_seat_io(
            {
                "run_id": "rf",
                "task_id": "tf",
                "role": "developer",
                "kind": "execute",
                "prompt": "P" * 5000,
                "system": "S",
                "response": "R",
            }
        )
        with TestClient(app) as client:
            payload = client.get("/monitor/raho/feed", params={"run_id": "rf"}).json()

        assert payload["source"] == "memory"
        row = payload["items"][0]
        assert "prompt" not in row
        assert row["prompt_length"] == 5000
        assert len(row["prompt_preview"]) == 320
        assert payload["total_roles"] == 1
        assert payload["runs"][0]["run_id"] == "rf"

    def test_full_and_detail_endpoints(self):
        from backend.main import app

        row = record_seat_io(
            {"run_id": "rg", "role": "developer", "kind": "execute", "prompt": "PP", "response": "RR", "system": "SS"}
        )
        with TestClient(app) as client:
            full = client.get("/monitor/raho/feed", params={"run_id": "rg", "full": "true"}).json()
            detail = client.get(f"/monitor/raho/seat/{row['io_id']}")
            missing = client.get("/monitor/raho/seat/nope")

        assert full["items"][0]["prompt"] == "PP"
        assert detail.json()["system"] == "SS"
        assert missing.status_code == 404

    def test_falls_back_to_disk_when_buffer_cleared(self):
        from backend.main import app

        record_seat_io({"run_id": "rd", "role": "developer", "prompt": "P", "response": "R"})
        STORE.clear()
        with TestClient(app) as client:
            payload = client.get("/monitor/raho/feed", params={"run_id": "rd"}).json()
        assert payload["source"] == "disk"
        assert len(payload["items"]) == 1
