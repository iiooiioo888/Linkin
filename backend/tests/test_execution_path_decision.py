"""用戶決策執行路徑：明示不被建議覆蓋、建議不建任務、缺策略拒絕、關鍵詞鎖定、兜底與四種 decision_source。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.api.routers import tasks as tasks_router
from backend.core.execution_path import (
    decide_task_execution,
    resolve_execution_path,
    suggest_execution_path,
)
from backend.core.execution_path_config import ExecutionPathConfig, save_execution_path_config
from backend.core.llm import call_llm
from backend.main import app
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
