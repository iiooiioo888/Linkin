"""Minecraft MCP 橋接：乾跑、護欄、公司工具註冊、靈境 API。"""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.company.tools import ToolCallRequest, tool_registry
from backend.linkin.api import register_linkin
from backend.linkin.constitution import reset_cache as reset_constitution_cache
from backend.linkin.knowledge import reset_store
from backend.linkin.minecraft import execute_for_agent, execute_named_tool
from backend.linkin.tools import ToolValidationError
from backend.tools import minecraft_mcp as mcp


@pytest.fixture()
def linkin_env(tmp_path, monkeypatch):
    monkeypatch.setenv("EVOL_LINKIN_DATA_DIR", str(tmp_path / "linkin"))
    monkeypatch.setenv("EVOL_LINKIN_CONSTITUTION_PATH", str(tmp_path / "linkin_constitution.json"))
    monkeypatch.setenv("EVOL_LINKIN_CHROMA_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("EVOL_LINKIN_FORCE_JSON", "1")
    monkeypatch.setenv("EVOL_MC_MCP_AUDIT_PATH", str(tmp_path / "mcp_audit.jsonl"))
    reset_store()
    reset_constitution_cache()
    yield tmp_path
    reset_store()
    reset_constitution_cache()


@pytest.fixture()
def client(linkin_env):
    app = FastAPI()
    register_linkin(app)
    with TestClient(app) as c:
        yield c


def test_is_minecraft_control_query():
    assert mcp.is_minecraft_control_query("在坐标(100, 64, 200)处放置一个钻石块") is True
    assert mcp.is_minecraft_control_query("使用 place_block") is True
    assert mcp.is_minecraft_control_query("測試問題") is False
    assert mcp.is_minecraft_control_query("請放置檔案") is False


def test_place_block_dry_run(tmp_path, monkeypatch):
    monkeypatch.setenv("EVOL_MC_MCP_ENABLED", "false")
    monkeypatch.setenv("EVOL_MC_MCP_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    result = mcp.place_block(100, 64, 200, "钻石块")
    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["remote"] == "pose_block"
    assert result["arguments"]["material"] == "DIAMOND_BLOCK"
    rows = mcp.recent_audit(5)
    assert rows and rows[-1]["tool"] == "place_block"


def test_fill_volume_limit():
    with pytest.raises(ToolValidationError) as exc:
        execute_named_tool(
            "fill_block",
            {"x1": 0, "y1": 0, "z1": 0, "x2": 100, "y2": 50, "z2": 100, "material": "STONE"},
        )
    assert exc.value.code == "block_limit"


def test_execute_command_needs_confirmation():
    with pytest.raises(ToolValidationError) as exc:
        execute_named_tool("execute_command", {"command": "ban Steve"})
    assert exc.value.code == "needs_confirmation"
    text = execute_for_agent("execute_command", command="ban Steve")
    payload = json.loads(text)
    assert payload["ok"] is False
    assert payload["code"] == "needs_confirmation"


def test_file_tool_blocked():
    result = mcp.call_mcp_tool("write_file", {"path": "ops.txt", "content": "x"})
    assert result["ok"] is False
    assert result["code"] == "file_tool_blocked"


def test_live_jsonrpc_posts_pose_block(monkeypatch):
    monkeypatch.setenv("EVOL_MC_MCP_ENABLED", "true")
    monkeypatch.setenv("EVOL_MC_MCP_TOKEN", "secret-token")
    monkeypatch.setenv("EVOL_MC_MCP_URL", "http://127.0.0.1:3000")

    captured: dict[str, object] = {}

    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"content": [{"type": "text", "text": "placed"}]},
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def close(self):
            return None

        def post(self, url, json=None, headers=None):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return FakeResp()

    monkeypatch.setattr(httpx, "Client", FakeClient)
    result = mcp.place_block(10, 64, 20, "DIAMOND_BLOCK")
    assert result["ok"] is True
    assert result["dry_run"] is False
    assert "token=secret-token" in str(captured["url"])
    assert captured["json"]["method"] == "tools/call"
    assert captured["json"]["params"]["name"] == "pose_block"
    assert captured["json"]["params"]["arguments"]["x"] == 10


def test_company_registry_has_minecraft_tools():
    names = {t.name for t in tool_registry.list_tools()}
    for expected in ("place_block", "pose_block", "break_block", "fill_block", "execute_command", "get_player"):
        assert expected in names


def test_role_permissions_for_minecraft_tools():
    place = tool_registry.get("place_block")
    assert place is not None
    assert tool_registry._role_permitted(place, "manager") is True
    assert tool_registry._role_permitted(place, "story_writer") is True
    assert tool_registry._role_permitted(place, "custom_linkin_build_executor") is True
    assert tool_registry._role_permitted(place, "developer") is False

    admin = tool_registry.get("execute_command")
    assert admin is not None
    assert tool_registry._role_permitted(admin, "manager") is True
    assert tool_registry._role_permitted(admin, "story_writer") is False

    denied = tool_registry.execute(
        ToolCallRequest(tool="place_block", args={"x": 1, "y": 2, "z": 3, "material": "STONE"}),
        role="developer",
    )
    assert denied.success is False

    allowed = tool_registry.execute(
        ToolCallRequest(tool="place_block", args={"x": 1, "y": 2, "z": 3, "material": "STONE"}),
        role="manager",
    )
    assert allowed.success is True
    payload = json.loads(str(allowed.result))
    assert payload["dry_run"] is True


def test_catalog_allowed_filters_tools():
    prompt = tool_registry.format_tools_prompt("manager", catalog_allowed=["place_block"])
    assert "place_block" in prompt
    assert "execute_command" not in prompt
    denied = tool_registry.execute(
        ToolCallRequest(tool="execute_command", args={"command": "time set day", "confirmed": True}),
        role="manager",
        catalog_allowed=["place_block"],
    )
    assert denied.success is False


def test_developer_prompt_hides_minecraft_write():
    from backend.company.orchestrator import CompanyOrchestrator
    from backend.company.state import RoleType
    from backend.services.docker_manager import DockerManager

    text = CompanyOrchestrator(docker_manager=DockerManager())._get_docker_tools_for_role(RoleType.DEVELOPER)
    assert "place_block" not in text
    assert "docker_ps" in text


def test_story_writer_prompt_includes_place_block():
    from backend.company.orchestrator import CompanyOrchestrator
    from backend.company.state import RoleType
    from backend.services.docker_manager import DockerManager

    text = CompanyOrchestrator(docker_manager=DockerManager())._get_docker_tools_for_role(RoleType.STORY_WRITER)
    assert "place_block" in text
    assert "pose_block" in text


def test_minecraft_api_status_and_call(client: TestClient):
    status = client.get("/linkin/minecraft/status")
    assert status.status_code == 200
    body = status.json()
    assert body["dry_run"] is True
    assert body["provider"] == "minemcp"
    assert "place_block" in body["company_tools"]

    placed = client.post(
        "/linkin/minecraft/call",
        json={"tool": "place_block", "arguments": {"x": 100, "y": 64, "z": 200, "material": "钻石块"}},
    )
    assert placed.status_code == 200
    assert placed.json()["ok"] is True
    assert placed.json()["dry_run"] is True
    assert placed.json()["params"]["material"] == "DIAMOND_BLOCK"

    banned = client.post("/linkin/minecraft/call", json={"tool": "execute_command", "arguments": {"command": "stop"}})
    assert banned.status_code == 409


def test_building_dispatch_dry_run(client: TestClient, monkeypatch):
    from backend.core.evaluation import DimensionResult, EvaluationResult

    def _pass(_q, _a):
        result = EvaluationResult(source="test")
        for dim in ("accuracy", "completeness", "clarity", "relevance"):
            setattr(result, dim, DimensionResult(9.5, "ok"))
        result.overall = 9.5
        return result

    monkeypatch.setattr("backend.linkin.knowledge.evaluate_for_write", _pass)
    created = client.post(
        "/linkin/buildings/generate",
        json={
            "prompt": "在林冠间搭建一座月光庭园小桥",
            "style": "精灵古典",
            "location": "120, 64, -300",
            "region": "精灵森林",
            "block_count": 40,
        },
    )
    assert created.status_code == 200
    bld_id = created.json()["building"]["id"]
    dispatched = client.post(f"/linkin/buildings/{bld_id}/dispatch")
    assert dispatched.status_code == 200
    assert dispatched.json()["minecraft"]["ok"] is True
    assert dispatched.json()["minecraft"]["dry_run"] is True
    assert dispatched.json()["building"]["status"] == "dispatched"


def test_admin_execute_includes_minecraft(client: TestClient):
    allowed = client.post("/linkin/admin/execute", json={"command": "time set day"})
    assert allowed.status_code == 200
    body = allowed.json()
    assert body["executed"] is True
    assert body["minecraft"]["ok"] is True
    assert body["minecraft"]["dry_run"] is True


def test_overview_includes_minecraft(client: TestClient):
    ov = client.get("/linkin/overview")
    assert ov.status_code == 200
    assert "minecraft" in ov.json()["compliance"]
    assert ov.json()["minecraft"]["dry_run"] is True


def test_seed_assigns_minecraft_tools(linkin_env):
    from backend.company.role_catalog import get_snapshot
    from backend.linkin.roles import seed_linkin_roles

    seed_linkin_roles()
    director = get_snapshot("custom_linkin_build_director")
    assert director is not None
    assert "place_block" in director["tools_allowed"]
    assert "execute_command" in director["tools_allowed"]
    executor = get_snapshot("custom_linkin_build_executor")
    assert executor is not None
    assert "place_block" in executor["tools_allowed"]
    assert "execute_command" not in executor["tools_allowed"]


def test_route_minecraft_query_to_company():
    from backend.core.company_nodes import route_by_complexity

    assert route_by_complexity({"query": "在坐标(100, 64, 200)处放置一个钻石块"}) == "run_company"
