"""實驗室整合工具測試。"""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import lab_tools


def test_firecrawl_scrape_basic_mode(monkeypatch):
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)

    class FakeResp:
        status_code = 200
        text = "<html><title>Demo</title><body><p>Hello</p></body></html>"

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, headers=None):
            return FakeResp()

    monkeypatch.setattr(httpx, "Client", FakeClient)
    result = lab_tools.firecrawl_scrape("https://example.com/page")
    assert result["source"] == "basic"
    assert "Hello" in result["markdown"]
    assert result["title"] == "Demo"


def test_optimize_prompt(monkeypatch):
    monkeypatch.setattr(
        lab_tools,
        "call_llm",
        lambda prompt, system=None, **kw: "優化後提示詞",
    )
    out = lab_tools.optimize_prompt("原始", mode="user", goal="更簡潔")
    assert out["optimized"] == "優化後提示詞"
    assert out["original"] == "原始"


def test_ponytail_review_parses_json(monkeypatch):
    payload = {
        "summary": "可刪 wrapper",
        "severity": "high",
        "delete_list": ["flatpickr"],
        "keep_list": ["input type=date"],
        "suggested_rewrite": "<input type=\"date\">",
    }
    monkeypatch.setattr(
        lab_tools,
        "call_llm",
        lambda prompt, system=None, **kw: json.dumps(payload, ensure_ascii=False),
    )
    out = lab_tools.ponytail_review("<div>...</div>", kind="code")
    assert out["review"]["severity"] == "high"
    assert "flatpickr" in out["review"]["delete_list"][0]


def test_get_evoloop_architecture():
    ir = lab_tools.get_evoloop_architecture()
    assert ir["meta"]["type"] == "architecture"
    assert any(n["id"] == "graph" for n in ir["nodes"])


def test_generate_architecture(monkeypatch):
    ir = {
        "meta": {"title": "Test", "type": "architecture"},
        "nodes": [{"id": "a", "label": "A", "role": "api"}],
        "edges": [],
    }
    monkeypatch.setattr(
        lab_tools,
        "call_llm",
        lambda prompt, system=None, **kw: json.dumps(ir),
    )
    out = lab_tools.generate_architecture("Browser -> API")
    assert out["nodes"][0]["id"] == "a"


@pytest.fixture
def client():
    return TestClient(app)


def test_lab_api_endpoints(client: TestClient, monkeypatch):
    monkeypatch.setattr(
        lab_tools,
        "firecrawl_scrape",
        lambda url, **kw: {"url": url, "title": "T", "markdown": "md", "source": "basic"},
    )
    monkeypatch.setattr(
        lab_tools,
        "optimize_prompt",
        lambda prompt, **kw: {"original": prompt, "optimized": "opt", "mode": "user"},
    )
    monkeypatch.setattr(
        lab_tools,
        "ponytail_review",
        lambda content, **kw: {"kind": "code", "review": {"summary": "ok"}, "source": "ponytail"},
    )
    monkeypatch.setattr(lab_tools, "get_evoloop_architecture", lab_tools.get_evoloop_architecture)

    r = client.post("/lab/firecrawl/scrape", json={"url": "https://example.com"})
    assert r.status_code == 200
    assert r.json()["markdown"] == "md"

    r = client.post("/lab/prompt/optimize", json={"prompt": "hi"})
    assert r.status_code == 200
    assert r.json()["optimized"] == "opt"

    r = client.post("/lab/ponytail/review", json={"content": "code"})
    assert r.status_code == 200
    assert r.json()["review"]["summary"] == "ok"

    r = client.get("/lab/archify/evoloop")
    assert r.status_code == 200
    assert r.json()["meta"]["title"]


def test_company_tool_registry_includes_lab_tools():
    from backend.company.tools import tool_registry

    names = {t.name for t in tool_registry.list_tools()}
    for expected in (
        "firecrawl_scrape",
        "firecrawl_search",
        "optimize_prompt",
        "ponytail_review",
        "archify_generate",
        "archify_evoloop",
        "place_block",
        "execute_command",
    ):
        assert expected in names
