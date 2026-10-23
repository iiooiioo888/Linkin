"""Agent 技能包同步至 Linkin 運行時的測試。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.company.agent_skills_sync import (
    build_skill_record,
    classify_skill_type,
    discover_agent_skill_dirs,
    parse_skill_frontmatter,
    sync_agent_skills,
)
from backend.company.mcp_clients import McpRegistry
from backend.company.skills import SkillsStore


class TestParseSkillFrontmatter:
    def test_parses_yaml_header(self):
        text = '---\nname: demo\ndescription: "Do things"\n---\n\nBody here'
        meta, body = parse_skill_frontmatter(text)
        assert meta["name"] == "demo"
        assert meta["description"] == "Do things"
        assert body == "Body here"

    def test_no_frontmatter(self):
        meta, body = parse_skill_frontmatter("plain markdown")
        assert meta == {}
        assert body == "plain markdown"

    def test_folded_description_skips_nested_map(self):
        text = (
            "---\n"
            "name: agent-reach\n"
            "description: >\n"
            "  MUST USE this\n"
            "  and that.\n"
            "\n"
            "  Second paragraph.\n"
            "metadata:\n"
            "  homepage: https://example.com\n"
            "---\n"
            "\n"
            "Body\n"
        )
        meta, body = parse_skill_frontmatter(text)
        assert meta["name"] == "agent-reach"
        assert meta["description"] == "MUST USE this and that.\nSecond paragraph."
        assert "homepage" not in meta
        assert "metadata" not in meta
        assert body == "Body"

    def test_vendored_agent_reach_skill(self):
        path = Path(".agents/skills/agent-reach/SKILL.md")
        meta, body = parse_skill_frontmatter(path.read_text(encoding="utf-8"))
        assert meta["name"] == "agent-reach"
        assert meta["description"].startswith("MUST USE")
        assert "小紅書" in body
        assert "mediacrawler" in body
        assert classify_skill_type("agent-reach", meta) == "cli-stub"


class TestClassifySkillType:
    def test_cursor_only(self):
        assert classify_skill_type("setup", {"disable-model-invocation": "true"}) == "cursor-only"
        assert classify_skill_type("x", {"hidden": "true"}) == "cursor-only"

    def test_cli_stub(self):
        assert classify_skill_type("agent-browser", {}) == "cli-stub"
        assert classify_skill_type("agent-reach", {}) == "cli-stub"
        assert classify_skill_type("just-scrape", {}) == "cli-stub"
        assert classify_skill_type("cli-anything", {}) == "cli-stub"

    def test_agent_pack_default(self):
        assert classify_skill_type("code-review", {"description": "review"}) == "agent-pack"


@pytest.fixture()
def mini_agents_tree(tmp_path):
    root = tmp_path / ".agents" / "skills"
    (root / "demo-skill").mkdir(parents=True)
    (root / "demo-skill" / "SKILL.md").write_text(
        "---\nname: Demo Skill\ndescription: When demoing\n---\n\nStep one\n",
        encoding="utf-8",
    )
    (root / "agent-browser").mkdir(parents=True)
    (root / "agent-browser" / "SKILL.md").write_text(
        "---\nname: agent-browser\nhidden: true\n---\n\nStub\n",
        encoding="utf-8",
    )
    lock = tmp_path / "skills-lock.json"
    lock.write_text(
        json.dumps(
            {
                "version": 1,
                "skills": {
                    "demo-skill": {
                        "source": "mattpocock/skills",
                        "computedHash": "abc123",
                    },
                    "agent-browser": {
                        "source": "vercel-labs/agent-browser",
                        "computedHash": "def456",
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    manifest = tmp_path / "agent_mcp_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "servers": [
                    {
                        "id": "linear",
                        "name": "Linear MCP",
                        "transport": "http",
                        "url": "https://mcp.linear.app/mcp",
                        "enabled": False,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return tmp_path, root, lock, manifest


class TestAgentSkillsSync:
    def test_discover_dirs(self, mini_agents_tree):
        _, root, _, _ = mini_agents_tree
        ids = [p.name for p in discover_agent_skill_dirs(root)]
        assert "demo-skill" in ids
        assert "agent-browser" in ids

    def test_build_record(self, mini_agents_tree):
        _, root, lock_path, _ = mini_agents_tree
        lock = json.loads(lock_path.read_text())["skills"]
        row = build_skill_record(root / "demo-skill", lock, root=root)
        assert row is not None
        assert row["skill_id"] == "demo-skill"
        assert row["source"] == "mattpocock/skills"
        assert row["skill_type"] == "agent-pack"

    def test_sync_creates_and_preserves_enabled(self, mini_agents_tree, tmp_path):
        base, root, lock_path, manifest_path = mini_agents_tree
        store = SkillsStore(path=tmp_path / "skills.json")
        registry = McpRegistry(path=tmp_path / "mcp_servers.json")

        report = sync_agent_skills(
            store,
            registry,
            skills_root=root,
            lock_path=lock_path,
            mcp_manifest_path=manifest_path,
        )
        assert report.skills_created == 2
        assert report.mcp_created == 1
        skills = {s.id: s for s in store.list()}
        assert skills["demo-skill"].managed is True
        assert skills["demo-skill"].enabled is False
        assert skills["agent-browser"].skill_type == "cursor-only"
        assert registry.get("linear") is not None

        store.set_enabled("demo-skill", True)
        lock = json.loads(lock_path.read_text())
        lock["skills"]["demo-skill"]["computedHash"] = "updated-hash"
        lock_path.write_text(json.dumps(lock), encoding="utf-8")

        report2 = sync_agent_skills(
            store,
            registry,
            skills_root=root,
            lock_path=lock_path,
            mcp_manifest_path=manifest_path,
        )
        assert report2.skills_updated == 1
        assert store.get("demo-skill").enabled is True
        assert store.get("demo-skill").content_hash == "updated-hash"

    def test_sync_skips_user_skill_with_same_id(self, mini_agents_tree, tmp_path):
        _, root, lock_path, manifest_path = mini_agents_tree
        store = SkillsStore(path=tmp_path / "skills.json")
        store.upsert("demo-skill", "user content", description="mine")
        registry = McpRegistry(path=tmp_path / "mcp_servers.json")

        report = sync_agent_skills(
            store,
            registry,
            skills_root=root,
            lock_path=lock_path,
            mcp_manifest_path=manifest_path,
        )
        assert report.skills_skipped >= 1
        assert store.get("demo-skill").content == "user content"
        assert store.get("demo-skill").managed is False

    def test_cli_anything_starts_enabled_and_keeps_later_choice(self, tmp_path):
        root = tmp_path / ".agents" / "skills" / "cli-anything"
        root.mkdir(parents=True)
        (root / "SKILL.md").write_text(
            "---\nname: cli-anything\ndescription: hub\n---\n\nUse cli-hub list.\n",
            encoding="utf-8",
        )
        lock = tmp_path / "skills-lock.json"
        lock.write_text(
            json.dumps(
                {
                    "version": 1,
                    "skills": {
                        "cli-anything": {
                            "source": "HKUDS/CLI-Anything",
                            "computedHash": "abc",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        manifest = tmp_path / "agent_mcp_manifest.json"
        manifest.write_text(json.dumps({"servers": []}), encoding="utf-8")
        store = SkillsStore(path=tmp_path / "skills.json")
        registry = McpRegistry(path=tmp_path / "mcp_servers.json")
        kwargs = {
            "skills_root": root.parent,
            "lock_path": lock,
            "mcp_manifest_path": manifest,
            "sync_mcp": False,
        }
        sync_agent_skills(store, registry, **kwargs)
        assert store.get("cli-anything").enabled is True
        assert store.get("cli-anything").skill_type == "cli-stub"
        store.set_enabled("cli-anything", False)
        sync_agent_skills(store, registry, **kwargs)
        assert store.get("cli-anything").enabled is False
