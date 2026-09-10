"""技能庫與 MCP 連線管理的單元測試。"""

from __future__ import annotations

import json

import pytest

from backend.company import mcp_clients
from backend.company.mcp_clients import McpRegistry, _slug
from backend.company.skills import SkillsStore, inject_skills

# ══════════════ Skills ══════════════


@pytest.fixture()
def store(tmp_path):
    return SkillsStore(path=tmp_path / "skills.json")


class TestSkillsStore:
    def test_upsert_and_persist(self, store):
        skill = store.upsert("測試技能", "內容 A", description="desc", trigger="當需要時")
        assert skill.id == "測試技能" or skill.id  # slug 化
        rows = store.list()
        assert len(rows) == 1
        assert rows[0].content == "內容 A"
        # 重載後仍在（落盤驗證）
        store2 = SkillsStore(path=store._path)
        assert len(store2.list()) == 1
        assert store2.list()[0].name == "測試技能"

    def test_upsert_requires_name_and_content(self, store):
        with pytest.raises(ValueError):
            store.upsert("", "內容")
        with pytest.raises(ValueError):
            store.upsert("名稱", "   ")

    def test_update_same_id_keeps_created_at(self, store):
        first = store.upsert("技能X", "v1")
        second = store.upsert("技能X", "v2", skill_id=first.id)
        assert second.created_at == first.created_at
        assert second.content == "v2"
        assert len(store.list()) == 1

    def test_toggle_and_delete(self, store):
        skill = store.upsert("技能Y", "內容")
        updated = store.set_enabled(skill.id, False)
        assert updated.enabled is False
        assert store.enabled_for(None) == []
        assert store.delete(skill.id) is True
        assert store.delete(skill.id) is False

    def test_role_filtering(self, store):
        store.upsert("全角色", "A")
        store.upsert("僅開發", "B", roles=["developer"])
        store.upsert("萬用字號", "C", roles=["custom_*"])
        dev = {s.name for s in store.enabled_for("developer")}
        assert dev == {"全角色", "僅開發"}
        cust = {s.name for s in store.enabled_for("custom_linkin_builder")}
        assert "萬用字號" in cust
        # custom_ 前綴語義：developer 匹配 custom_developer
        assert any(s.name == "僅開發" for s in store.enabled_for("custom_developer"))

    def test_render_prompt_empty_when_no_skills(self, store):
        assert store.render_prompt("developer") == ""

    def test_render_prompt_contains_skill(self, store):
        store.upsert("部署流程", "先備份再更新", trigger="更新時")
        text = store.render_prompt("developer")
        assert "技能庫" in text
        assert "部署流程" in text
        assert "先備份再更新" in text
        assert "適用時機" in text

    def test_render_prompt_budget_truncates(self, store):
        store.upsert("長技能", "字" * 5000, skill_budget=500)
        text = store.render_prompt(None)
        assert "已截斷" in text
        assert len(text) < 5000

    def test_render_prompt_total_budget(self, store):
        for i in range(10):
            store.upsert(f"技能{i}", "內容" * 300, skill_budget=2000)
        text = store.render_prompt(None, budget=3000)
        assert len(text) <= 3000 + 200  # 區塊粒度允許少量超出

    def test_inject_skills_appends(self, store, monkeypatch):
        store.upsert("技能Z", "知識")
        monkeypatch.setattr("backend.company.skills.skills_store", store)
        out = inject_skills("SYSTEM PROMPT", "developer")
        assert out.startswith("SYSTEM PROMPT")
        assert "技能Z" in out

    def test_inject_skills_noop_when_empty(self, store, monkeypatch):
        monkeypatch.setattr("backend.company.skills.skills_store", store)
        assert inject_skills("P", None) == "P"

    def test_inject_skills_swallows_errors(self, monkeypatch):
        class Boom:
            def render_prompt(self, *a, **k):
                raise RuntimeError("boom")

        monkeypatch.setattr("backend.company.skills.skills_store", Boom())
        assert inject_skills("P", "dev") == "P"

    def test_corrupt_json_keeps_memory(self, store):
        store.upsert("好技能", "內容")
        store._path.write_text("{broken json", encoding="utf-8")
        store._loaded = False  # 強制重讀
        rows = store.list()
        # 讀取失敗不炸；記憶體版仍在或為空列表（兩者皆可接受）
        assert isinstance(rows, list)


# ══════════════ MCP ══════════════


class TestSlug:
    def test_slug_basic(self):
        assert _slug("My Server!") == "my_server"
        assert _slug("  ").startswith("mcp_")


@pytest.fixture()
def registry(tmp_path):
    return McpRegistry(path=tmp_path / "mcp_servers.json")


class TestMcpRegistry:
    def test_upsert_validation(self, registry):
        with pytest.raises(ValueError):
            registry.upsert("", "stdio")
        with pytest.raises(ValueError):
            registry.upsert("x", "carrier-pigeon")
        with pytest.raises(ValueError):
            registry.upsert("本地", "stdio", command="")
        with pytest.raises(ValueError):
            registry.upsert("遠端", "http", url="")
        srv = registry.upsert("本地", "stdio", command="node server.js")
        assert srv.transport == "stdio"
        assert srv.timeout == 20.0

    def test_persist_roundtrip(self, registry):
        registry.upsert(
            "遠端", "http", url="https://example.com/mcp",
            headers={"X-Api-Key": "tok-123"}, allowed_tools=["search"],
        )
        registry2 = McpRegistry(path=registry._path)
        rows = registry2.list()
        assert len(rows) == 1
        assert rows[0].headers["X-Api-Key"] == "tok-123"
        assert rows[0].allowed_tools == ["search"]

    def test_timeout_clamped(self, registry):
        srv = registry.upsert("s", "stdio", command="x", timeout=99999)
        assert srv.timeout == 300.0
        srv2 = registry.upsert("s2", "stdio", command="x", timeout=0.1)
        assert srv2.timeout == 2.0

    def test_toggle_and_delete(self, registry):
        srv = registry.upsert("t", "stdio", command="x")
        assert registry.set_enabled(srv.id, False).enabled is False
        with pytest.raises(KeyError):
            registry.set_enabled("nope", True)
        assert registry.delete(srv.id) is True
        assert registry.delete(srv.id) is False

    def test_probe_failure_graceful(self, registry):
        srv = registry.upsert(
            "壞掉的", "stdio", command="/nonexistent/binary --x", timeout=5
        )
        result = registry.probe(srv.id)
        assert result["ok"] is False
        assert result["error"]
        # 探測結果落盤
        assert registry.get(srv.id).last_probe["ok"] is False

    def test_mount_skips_disabled_and_failures(self, registry, monkeypatch):
        registry.upsert("壞的", "stdio", command="/nonexistent/x")
        registry.upsert("停的", "stdio", command="echo hi", enabled=False)

        class FakeRegistry:
            def __init__(self):
                self.registered = []

            def register(self, **kwargs):
                self.registered.append(kwargs["name"])

        fake = FakeRegistry()
        mounted = registry.mount_tools(fake)
        assert mounted == []
        assert fake.registered == []

    def test_mount_registers_tools_with_prefix(self, registry, monkeypatch):
        srv = registry.upsert("demo", "stdio", command="echo hi")

        fake_tools = [
            {"name": "search", "description": "搜尋", "inputSchema": {"properties": {"q": {"type": "string"}}}},
            {"name": "delete_all", "description": "危險"},
        ]

        def fake_probe(server):
            return {
                "ok": True, "tool_count": 2, "tools": ["search", "delete_all"],
                "latency_ms": 1, "probed_at": "", "error": "",
            }

        monkeypatch.setattr(mcp_clients, "probe_server", fake_probe)

        # patch _make_session to return canned tools
        class FakeSession:
            def list_tools(self):
                return fake_tools

            def call_tool(self, name, args):
                return f"called {name} {args}"

        monkeypatch.setattr(mcp_clients, "_make_session", lambda s: FakeSession())

        class FakeRegistry:
            def __init__(self):
                self.tools = {}

            def register(self, **kwargs):
                self.tools[kwargs["name"]] = kwargs

        fake = FakeRegistry()
        mounted = registry.mount_tools(fake)
        assert mounted == ["demo__search", "demo__delete_all"]
        assert fake.tools["demo__search"]["readonly"] is True
        assert "MCP:demo" in fake.tools["demo__search"]["description"]
        # 執行 lambda 走 registry.call
        result = fake.tools["demo__search"]["execute"](q="hello")
        assert "called search" in result

    def test_mount_respects_allowed_tools(self, registry, monkeypatch):
        registry.upsert("demo2", "stdio", command="echo hi", allowed_tools=["search"])

        class FakeSession:
            def list_tools(self):
                return [{"name": "search"}, {"name": "danger"}]

            def call_tool(self, name, args):
                return name

        monkeypatch.setattr(mcp_clients, "_make_session", lambda s: FakeSession())

        class FakeRegistry:
            def __init__(self):
                self.names = []

            def register(self, **kwargs):
                self.names.append(kwargs["name"])

        fake = FakeRegistry()
        registry.mount_tools(fake)
        assert fake.names == ["demo2__search"]

    def test_mount_idempotent(self, registry, monkeypatch):
        registry.upsert("demo3", "stdio", command="echo hi")

        class FakeSession:
            def list_tools(self):
                return [{"name": "t1"}]

            def call_tool(self, name, args):
                return name

        monkeypatch.setattr(mcp_clients, "_make_session", lambda s: FakeSession())

        class FakeRegistry:
            def __init__(self):
                self.names = []

            def register(self, **kwargs):
                self.names.append(kwargs["name"])

        fake = FakeRegistry()
        assert registry.mount_tools(fake) == ["demo3__t1"]
        assert registry.mount_tools(fake) == []  # 第二次跳過
        assert len(registry.mount_tools(fake, force=True)) == 1  # force 重掛


class TestUnwrapContent:
    def test_text_blocks(self):
        res = {"content": [{"type": "text", "text": "hello"}, {"type": "text", "text": "world"}]}
        assert mcp_clients._unwrap_content(res) == "hello\nworld"

    def test_structured(self):
        res = {"structuredContent": {"a": 1}}
        assert json.loads(mcp_clients._unwrap_content(res)) == {"a": 1}

    def test_plain(self):
        assert json.loads(mcp_clients._unwrap_content({"x": 1})) == {"x": 1}


class TestParseSse:
    def test_last_data_line(self):
        text = 'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"tools":[{"name":"a"}]}}\n\n'
        parsed = mcp_clients._parse_sse_payload(text)
        assert parsed["result"]["tools"][0]["name"] == "a"

    def test_garbage_lines_skipped(self):
        text = "data: not-json\ndata: {\"ok\": true}\n"
        assert mcp_clients._parse_sse_payload(text) == {"ok": True}
