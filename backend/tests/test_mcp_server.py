"""對外 MCP server（backend/mcp_server.py）dispatcher 測試。"""

from __future__ import annotations

import json

import pytest

from backend import mcp_server


@pytest.fixture()
def token_env(monkeypatch):
    monkeypatch.setenv("EVOL_MCP_SERVER_TOKEN", "test-token-123")
    return "test-token-123"


class TestProtocol:
    def test_initialize(self):
        reply = mcp_server.handle_message({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                       "clientInfo": {"name": "t", "version": "0"}},
        })
        assert reply["id"] == 1
        assert reply["result"]["serverInfo"]["name"] == "linkin-evoloop"
        assert "tools" in reply["result"]["capabilities"]

    def test_initialized_notification_returns_none(self):
        assert mcp_server.handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None

    def test_tools_list(self):
        reply = mcp_server.handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = [t["name"] for t in reply["result"]["tools"]]
        assert "linkin_submit_task" in names
        assert "linkin_task_status" in names
        assert "linkin_skills_list" in names
        # 每個工具都有 schema
        for tool in reply["result"]["tools"]:
            assert "inputSchema" in tool

    def test_unknown_method_error(self):
        reply = mcp_server.handle_message({"jsonrpc": "2.0", "id": 3, "method": "bogus/method"})
        assert reply["error"]["code"] == -32601

    def test_unknown_method_notification_ignored(self):
        assert mcp_server.handle_message({"jsonrpc": "2.0", "method": "bogus/method"}) is None


class TestTools:
    def test_health(self):
        reply = mcp_server.handle_message({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "linkin_health", "arguments": {}},
        })
        payload = json.loads(reply["result"]["content"][0]["text"])
        assert payload["status"] == "ok"

    def test_submit_requires_query(self):
        reply = mcp_server.handle_message({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "linkin_submit_task", "arguments": {}},
        })
        assert reply["result"]["isError"] is True

    def test_task_status_missing(self):
        reply = mcp_server.handle_message({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "linkin_task_status", "arguments": {"task_id": "nope"}},
        })
        assert reply["result"]["isError"] is True

    def test_unknown_tool(self):
        reply = mcp_server.handle_message({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "rm_rf", "arguments": {}},
        })
        assert reply["result"]["isError"] is True
        assert "未知工具" in reply["result"]["content"][0]["text"]

    def test_submit_and_status_roundtrip(self, monkeypatch):
        from backend.services.task_manager import task_manager

        started: list[str] = []
        monkeypatch.setattr(
            task_manager, "start_task_from_thread",
            lambda record: started.append(record.task_id),
        )
        sub = mcp_server.handle_message({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "linkin_submit_task",
                       "arguments": {"query": "MCP 測試任務", "strategy": "simple"}},
        })
        payload = json.loads(sub["result"]["content"][0]["text"])
        tid = payload["task_id"]
        assert started == [tid]
        st = mcp_server.handle_message({
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "linkin_task_status", "arguments": {"task_id": tid}},
        })
        data = json.loads(st["result"]["content"][0]["text"])
        assert data["task_id"] == tid
        assert data["status"] in ("pending", "running", "completed", "failed", "cancelled")
        task_manager.tasks.pop(tid, None)

    def test_list_tasks(self):
        reply = mcp_server.handle_message({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "linkin_list_tasks", "arguments": {"limit": 5}},
        })
        rows = json.loads(reply["result"]["content"][0]["text"])
        assert isinstance(rows, list)
        assert len(rows) <= 5

    def test_skills_list(self):
        reply = mcp_server.handle_message({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "linkin_skills_list", "arguments": {}},
        })
        assert reply["result"]["isError"] is False
        json.loads(reply["result"]["content"][0]["text"])

    def test_skill_get_missing(self):
        reply = mcp_server.handle_message({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "linkin_skill_get", "arguments": {"skill_id": "nope"}},
        })
        assert reply["result"]["isError"] is True

    def test_tools_list_tool(self):
        reply = mcp_server.handle_message({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "linkin_tools_list", "arguments": {}},
        })
        rows = json.loads(reply["result"]["content"][0]["text"])
        assert any(r["name"] for r in rows)


class TestHttpAuth:
    def test_fail_closed_without_token(self, monkeypatch):
        monkeypatch.delenv("EVOL_MCP_SERVER_TOKEN", raising=False)
        assert mcp_server.check_http_token("anything") is False
        assert mcp_server.check_http_token(None) is False

    def test_token_match(self, token_env):
        assert mcp_server.check_http_token(token_env) is True
        assert mcp_server.check_http_token("wrong") is False
        assert mcp_server.check_http_token(None) is False
