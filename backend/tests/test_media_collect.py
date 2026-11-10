"""media-collect 契約：reuse 乾跑、缺口不抓取、下載不另開路徑。"""

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.mediacrawler.collect import dispatch_tool
from backend.mediacrawler.jobs import reset_job_manager

client = TestClient(app)


@pytest.fixture()
def mediacrawler_env(tmp_path, monkeypatch):
    home = tmp_path / "MediaCrawler"
    home.mkdir(exist_ok=True)
    (home / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (home / "pyproject.toml").write_text("[project]\nname='mc'\n", encoding="utf-8")
    monkeypatch.setenv("MEDIACRAWLER_HOME", str(home))
    monkeypatch.setenv("EVOL_MEDIACRAWLER_RESULTS_ROOT", str(tmp_path / "results"))
    monkeypatch.setenv("EVOL_MEDIACRAWLER_CONFIG", str(tmp_path / "runtime.json"))
    monkeypatch.setenv("EVOL_MEDIACRAWLER_JOBS_STORE", str(tmp_path / "jobs.json"))
    monkeypatch.setenv("EVOL_MEDIACRAWLER_ENABLED", "false")
    reset_job_manager()
    yield
    reset_job_manager()


def test_search_douyin_dry_run_submits_job(mediacrawler_env):
    result = dispatch_tool({"tool": "search_douyin", "query": "茶", "limit": 3})
    assert result["status"] == "submitted"
    assert result["platform"] == "dy"
    assert result["dry_run"] is True
    assert result["job"]["status"] == "completed"
    assert result["items"] == []
    assert "cookie" not in (result["job"].get("request") or {})


def test_search_xhs_creator(mediacrawler_env):
    result = dispatch_tool({"tool": "search_xhs", "creator_id": "abc"})
    assert result["platform"] == "xhs"
    assert result["job"]["request"]["crawl_type"] == "creator"


def test_gap_platforms_do_not_fetch():
    for tool in ("search_tiktok", "search_instagram", "search_x"):
        result = dispatch_tool({"tool": tool, "query": "tea"})
        assert result["status"] == "gap"
        assert result["items"] == []


def test_download_media_is_handoff_only():
    result = dispatch_tool(
        {
            "tool": "download_media",
            "platform": "dy",
            "source_url": "https://example.com/post",
            "asset_url": "https://example.com/a.jpg",
        }
    )
    assert result["fetched"] is False
    assert result["persist"] == "media_vault.ingest"


def test_rejects_cookie():
    try:
        dispatch_tool({"tool": "search_douyin", "query": "茶", "cookie": "a=b"})
    except ValueError as exc:
        assert "cookie" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_http_collect_gap(mediacrawler_env):
    response = client.post("/mediacrawler/collect", json={"tool": "search_x", "query": "tea"})
    assert response.status_code == 200
    assert response.json()["status"] == "gap"
