"""用戶決策執行路徑：明示不被建議覆蓋、建議不建任務、缺策略拒絕、關鍵詞鎖定、兜底與四種 decision_source。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.api.routers import tasks as tasks_router
from backend.core.execution_path import (
    EXECUTION_PATH_FIELDS,
    decide_task_execution,
    reason_text,
    resolve_execution_path,
    suggest_execution_path,
)
from backend.core.execution_path_config import ExecutionPathConfig, save_execution_path_config
from backend.core.llm import call_llm
from backend.main import app
from backend.services.trace_logger import read_trace
from backend.tenant.context import tenant_user_id

COMPLEX_Q = "請設計並實現一個完整的微服務系統架構"
PLC_Q = "請檢查 PLC 聯鎖是否異常"


def _no_llm(*_args, **_kwargs):
    raise AssertionError("選路測試不應呼叫 LLM")


@pytest.fixture
def no_llm(monkeypatch):
    monkeypatch.setattr("backend.core.llm.call_llm", _no_llm)
    monkeypatch.setattr("backend.core.llm.call_llm_stream", _no_llm)
    monkeypatch.setattr("backend.core.nodes.call_llm", _no_llm)
    monkeypatch.setattr(tasks_router.task_manager, "start_task", lambda _record: None)
    monkeypatch.setattr(tasks_router.task_manager, "start_budget_draft", lambda _record: None)
    return call_llm


def _client():
    return TestClient(app)


def _quiet_config() -> ExecutionPathConfig:
    return ExecutionPathConfig(force_company_keywords=())


class TestResolveDoesNotLetSuggestionOverrideChoice:
    def test_explicit_simple_beats_company_suggestion(self):
        cfg = _quiet_config()
        suggestion = suggest_execution_path(COMPLEX_Q, config=cfg)
        assert suggestion.suggested == "company"
        assert suggestion.locked is False

        chosen = resolve_execution_path(COMPLEX_Q, "auto", user_choice="simple", config=cfg)
        assert chosen.suggested == "simple"
        assert chosen.reason == "user_explicit"
        assert chosen.locked is False
        assert chosen == "simple"


class TestDecisionSources:
    def test_user_explicit(self):
        decision = decide_task_execution("你好", "company", config=_quiet_config())
        assert decision.created is True
        assert decision.suggested == "company"
        assert decision.decision_source == "user_explicit"
        assert decision.reason == "user_explicit"

    def test_user_default(self):
        cfg = ExecutionPathConfig(
            default_execution_strategy="company",
            force_company_keywords=(),
        )
        decision = decide_task_execution("你好", None, config=cfg)
        assert decision.decision_source == "user_default"
        assert decision.suggested == "company"
        assert decision.using_default is True
        assert decision.can_switch is True

    def test_admin_lock_overrides_explicit_simple(self):
        cfg = ExecutionPathConfig(force_company_keywords=("plc", "opc"))
        chosen = resolve_execution_path(PLC_Q, "simple", user_choice="simple", config=cfg)
        assert chosen.suggested == "company"
        assert chosen.locked is True
        assert chosen.reason == "admin_lock"

        decision = decide_task_execution(PLC_Q, "simple", config=cfg)
        assert decision.decision_source == "admin_lock"
        assert decision.suggested == "company"
        assert decision.locked is True
        assert decision.can_switch is False

    def test_fallback_simple_when_user_default_missing(self):
        decision = decide_task_execution("你好", "user_default", config=_quiet_config())
        assert decision.decision_source == "fallback"
        assert decision.suggested == "simple"
        assert decision.reason == "fallback"
        assert decision.locked is False


class TestTaskApi:
    def test_suggestion_endpoint_does_not_create_task(self, no_llm):
        del no_llm
        before = set(tasks_router.task_manager.tasks)
        with _client() as client:
            resp = client.get("/tasks/path-suggestion", params={"query": COMPLEX_Q})
        assert resp.status_code == 200
        body = resp.json()
        assert body["created"] is False
        assert body["task_id"] is None
        assert body["suggested"] == "company"
        assert body["locked"] is False
        assert body["reason"]
        assert set(tasks_router.task_manager.tasks) == before

    def test_missing_strategy_without_default_is_rejected(self, no_llm):
        del no_llm
        before = set(tasks_router.task_manager.tasks)
        with _client() as client:
            resp = client.post("/tasks", json={"query": "你好"})
        assert resp.status_code == 422
        assert "選擇" in resp.text
        assert set(tasks_router.task_manager.tasks) == before

    def test_auto_is_rejected(self, no_llm):
        del no_llm
        with _client() as client:
            resp = client.post(
                "/tasks",
                json={"query": "你好", "execution_strategy": "auto"},
            )
        assert resp.status_code == 422
        assert "auto" in resp.text

    def test_http_decision_sources(self, no_llm):
        del no_llm
        token = tenant_user_id.set("path_decision_user")
        created: list[str] = []
        try:
            save_execution_path_config(
                {
                    "default_execution_strategy": "company",
                    "force_company_keywords": ["plc", "opc"],
                },
                user_id="path_decision_user",
            )
            with _client() as client:
                headers = {"X-Linkin-Tenant-Override": "path_decision_user"}

                explicit = client.post(
                    "/tasks",
                    headers=headers,
                    json={"query": COMPLEX_Q, "execution_strategy": "simple"},
                )
                assert explicit.status_code == 200, explicit.text
                explicit_body = explicit.json()
                assert explicit_body["decision_source"] == "user_explicit"
                assert explicit_body["strategy"] == "simple"
                assert explicit_body["locked"] is False
                created.append(explicit_body["task_id"])
                stored = client.get(f"/tasks/{explicit_body['task_id']}", headers=headers)
                assert stored.status_code == 200, stored.text
                assert stored.json()["decision_source"] == "user_explicit"

                defaulted = client.post("/tasks", headers=headers, json={"query": "今天天氣如何"})
                assert defaulted.status_code == 200, defaulted.text
                default_body = defaulted.json()
                assert default_body["decision_source"] == "user_default"
                assert default_body["strategy"] == "company"
                assert default_body["using_default"] is True
                assert default_body["can_switch"] is True
                created.append(default_body["task_id"])

                locked = client.post(
                    "/tasks",
                    headers=headers,
                    json={"query": PLC_Q, "execution_strategy": "simple"},
                )
                assert locked.status_code == 200, locked.text
                locked_body = locked.json()
                assert locked_body["decision_source"] == "admin_lock"
                assert locked_body["strategy"] == "company"
                assert locked_body["locked"] is True
                created.append(locked_body["task_id"])

                save_execution_path_config(
                    {"clear_default": True, "force_company_keywords": []},
                    user_id="path_decision_user",
                )
                fallback = client.post(
                    "/tasks",
                    headers=headers,
                    json={"query": "你好", "execution_strategy": "user_default"},
                )
                assert fallback.status_code == 200, fallback.text
                fallback_body = fallback.json()
                assert fallback_body["decision_source"] == "fallback"
                assert fallback_body["strategy"] == "simple"
                created.append(fallback_body["task_id"])

                suggest = client.post(
                    "/tasks",
                    headers=headers,
                    json={"query": COMPLEX_Q, "execution_strategy": "suggest_only"},
                )
                assert suggest.status_code == 200, suggest.text
                assert suggest.json()["created"] is False
                assert suggest.json()["task_id"] is None
        finally:
            tenant_user_id.reset(token)
            for task_id in created:
                tasks_router.task_manager.tasks.pop(task_id, None)


class TestChatDoesNotExecuteAuto:
    def test_chat_rejects_auto_before_graph(self, no_llm, monkeypatch):
        del no_llm

        async def _boom(*_args, **_kwargs):
            raise AssertionError("auto 不應進入圖")

        monkeypatch.setattr("backend.api.routers.chat.routes.evoloop_graph.ainvoke", _boom)
        with _client() as client:
            resp = client.post("/chat", json={"query": "你好", "execution_strategy": "auto"})
        assert resp.status_code == 422
        assert "auto" in resp.text

    def test_stream_rejects_auto_and_suggest_only_without_creating_task(self, no_llm, monkeypatch):
        del no_llm

        def _boom(*_args, **_kwargs):
            raise AssertionError("拒絕的策略不應選路")

        monkeypatch.setattr(
            "backend.api.routers.chat.streaming.chat_stream_uses_company_sse",
            _boom,
        )
        before = set(tasks_router.task_manager.tasks)
        with _client() as client:
            auto = client.post(
                "/chat/stream",
                json={"query": COMPLEX_Q, "execution_strategy": "auto"},
            )
            suggest = client.post(
                "/chat/stream",
                json={"query": COMPLEX_Q, "execution_strategy": "suggest_only"},
            )
        assert auto.status_code == 422
        assert "auto" in auto.text
        assert suggest.status_code == 422
        assert "suggest_only" in suggest.text
        assert set(tasks_router.task_manager.tasks) == before

    def test_company_stream_persists_decision_source(self, no_llm, monkeypatch):
        del no_llm
        from backend.api.routers.chat import company_stream

        monkeypatch.setattr(company_stream.task_manager, "start_budget_draft", lambda _record: None)
        before = set(company_stream.task_manager.tasks)
        with _client() as client, client.stream(
            "POST",
            "/chat/stream",
            json={"query": "你好", "execution_strategy": "company"},
        ) as resp:
            assert resp.status_code == 200
            text = "".join(resp.iter_text())
        assert "user_explicit" in text
        created = set(company_stream.task_manager.tasks) - before
        assert len(created) == 1
        record = company_stream.task_manager.tasks[created.pop()]
        try:
            assert record.decision_source == "user_explicit"
            assert record.strategy == "company"
            assert record.resolved_path == "company"
        finally:
            company_stream.task_manager.tasks.pop(record.task_id, None)


def _path_structure(record: dict) -> list[tuple[str, str]]:
    return [(key, type(record[key]).__name__) for key in record]


def _task_execution_path(body: dict, query: str) -> dict:
    """把 POST /tasks 已回的決策投影成同步聊天的 execution_path。"""
    return {
        "chosen": body["strategy"],
        "source": body["decision_source"],
        "suggested": suggest_execution_path(query).suggested,
        "reason": reason_text(body["reason"]),
        "locked": body["locked"],
    }


def _stub_chat_graph(monkeypatch) -> None:
    async def _answer(_state):
        return {"current_answer": "已收到", "score": 9.0, "iteration": 0}

    monkeypatch.setattr("backend.api.routers.chat.routes.evoloop_graph.ainvoke", _answer)


def test_route_node_audits_decision_source(no_llm):
    """圖上既有 pipeline trace 要帶 decision_source，不只出現在回應裡。"""
    del no_llm
    from backend.core.company_nodes import route_by_complexity

    route_by_complexity(
        {
            "query": "你好",
            "execution_strategy": "simple",
            "session_id": "route_audit_simple",
        }
    )
    events = read_trace("route_audit_simple", limit=20)
    node = next(event for event in events if event.get("node") == "route_by_complexity")
    assert node["decision_source"] == "user_explicit"
    assert node["execution_path"] == "simple"


class TestSyncChatExecutionPath:
    def test_sync_and_async_execution_path_structure_match(self, no_llm, monkeypatch):
        del no_llm
        _stub_chat_graph(monkeypatch)
        token = tenant_user_id.set("sync_chat_structure")
        created: list[str] = []
        try:
            save_execution_path_config(
                {"clear_default": True, "force_company_keywords": []},
                user_id="sync_chat_structure",
            )
            headers = {"X-Linkin-Tenant-Override": "sync_chat_structure"}
            with _client() as client:
                chat = client.post(
                    "/chat",
                    headers=headers,
                    json={
                        "query": COMPLEX_Q,
                        "execution_strategy": "simple",
                        "session_id": "sync_structure",
                    },
                )
                task = client.post(
                    "/tasks",
                    headers=headers,
                    json={"query": COMPLEX_Q, "execution_strategy": "simple"},
                )
            assert chat.status_code == 200, chat.text
            assert task.status_code == 200, task.text
            created.append(task.json()["task_id"])
            sync_path = chat.json()["execution_path"]
            async_path = _task_execution_path(task.json(), COMPLEX_Q)
            assert _path_structure(sync_path) == _path_structure(async_path)
            assert list(sync_path) == list(EXECUTION_PATH_FIELDS)
        finally:
            tenant_user_id.reset(token)
            for task_id in created:
                tasks_router.task_manager.tasks.pop(task_id, None)

    @pytest.mark.parametrize(
        ("strategy", "query", "config", "source", "chosen", "locked"),
        [
            (
                "simple",
                COMPLEX_Q,
                {"clear_default": True, "force_company_keywords": []},
                "user_explicit",
                "simple",
                False,
            ),
            (
                "user_default",
                "你好",
                {"default_execution_strategy": "company", "force_company_keywords": []},
                "user_default",
                "company",
                False,
            ),
            (
                "simple",
                PLC_Q,
                {"force_company_keywords": ["plc", "opc"]},
                "admin_lock",
                "company",
                True,
            ),
            (
                "user_default",
                "你好",
                {"clear_default": True, "force_company_keywords": []},
                "fallback",
                "simple",
                False,
            ),
        ],
    )
    def test_source_is_audited_and_matches_task(
        self, no_llm, monkeypatch, strategy, query, config, source, chosen, locked
    ):
        del no_llm
        _stub_chat_graph(monkeypatch)
        user = f"sync_chat_{source}"
        token = tenant_user_id.set(user)
        created: list[str] = []
        session_id = f"sync_{source}"
        try:
            save_execution_path_config(config, user_id=user)
            headers = {"X-Linkin-Tenant-Override": user}
            with _client() as client:
                chat = client.post(
                    "/chat",
                    headers=headers,
                    json={
                        "query": query,
                        "execution_strategy": strategy,
                        "session_id": session_id,
                    },
                )
                task = client.post(
                    "/tasks",
                    headers=headers,
                    json={"query": query, "execution_strategy": strategy},
                )
            assert chat.status_code == 200, chat.text
            assert task.status_code == 200, task.text
            task_body = task.json()
            created.append(task_body["task_id"])
            path = chat.json()["execution_path"]
            assert path == _task_execution_path(task_body, query)
            assert path["source"] == source
            assert path["chosen"] == chosen
            assert path["locked"] is locked
            assert path["source"] in {"user_explicit", "user_default", "admin_lock", "fallback"}
            audited = [
                event.get("decision_source")
                for event in read_trace(session_id, limit=20)
                if event.get("event") == "execution_path"
            ]
            assert audited == [source]
        finally:
            tenant_user_id.reset(token)
            for task_id in created:
                tasks_router.task_manager.tasks.pop(task_id, None)
