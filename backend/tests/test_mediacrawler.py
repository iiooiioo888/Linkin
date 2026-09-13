"""MediaCrawler 整合：配置校驗、任務狀態機、路徑安全（mock 子進程）。"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.mediacrawler.config import (
    CrawlJobRequest,
    integration_status,
    validate_job_request,
)
from backend.mediacrawler.jobs import MediaCrawlerJobManager, build_command, reset_job_manager
from backend.mediacrawler.paths import safe_result_path
from backend.mediacrawler.service import start_job, validate_job


@pytest.fixture()
def mediacrawler_env(tmp_path, monkeypatch):
    home = tmp_path / "MediaCrawler"
    home.mkdir()
    (home / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (home / "pyproject.toml").write_text("[project]\nname='mc'\n", encoding="utf-8")
    results = tmp_path / "results"
    runtime = tmp_path / "runtime.json"
    jobs_store = tmp_path / "jobs.json"
    monkeypatch.setenv("MEDIACRAWLER_HOME", str(home))
    monkeypatch.setenv("EVOL_MEDIACRAWLER_RESULTS_ROOT", str(results))
    monkeypatch.setenv("EVOL_MEDIACRAWLER_CONFIG", str(runtime))
    monkeypatch.setenv("EVOL_MEDIACRAWLER_JOBS_STORE", str(jobs_store))
    monkeypatch.setenv("EVOL_MEDIACRAWLER_ENABLED", "false")
    reset_job_manager()
    yield {"home": home, "results": results, "runtime": runtime, "jobs_store": jobs_store}
    reset_job_manager()


def test_validate_job_request_requires_keywords(mediacrawler_env):
    req = CrawlJobRequest(platform="xhs", crawl_type="search", dry_run=True)
    errors = validate_job_request(req)
    assert any("keywords" in e for e in errors)


def test_validate_job_request_passes_dry_run(mediacrawler_env):
    req = CrawlJobRequest(platform="xhs", crawl_type="search", keywords="咖啡", dry_run=True)
    errors = validate_job_request(req)
    assert errors == []


def test_validate_job_request_blocks_real_run_when_disabled(mediacrawler_env):
    req = CrawlJobRequest(platform="xhs", crawl_type="search", keywords="咖啡", cookie="abc=1")
    errors = validate_job_request(req)
    assert any("EVOL_MEDIACRAWLER_ENABLED" in e for e in errors)


def test_build_command_uv_runner(mediacrawler_env):
    req = CrawlJobRequest(platform="xhs", crawl_type="search", keywords="咖啡", dry_run=True)
    cmd = build_command(req)
    assert cmd[:4] == ["uv", "run", "main.py", "--platform"]
    assert "xhs" in cmd
    assert "--type" in cmd and "search" in cmd


def test_job_manager_dry_run_completes(mediacrawler_env):
    mgr = MediaCrawlerJobManager()
    job = mgr.submit(CrawlJobRequest(platform="dy", crawl_type="search", keywords="測試", dry_run=True))
    assert job.status == "completed"
    assert job.dry_run is True
    assert Path(job.log_path).is_file()


@patch("backend.mediacrawler.jobs.subprocess.Popen")
def test_job_manager_real_run_success(mock_popen, mediacrawler_env, monkeypatch):
    monkeypatch.setenv("EVOL_MEDIACRAWLER_ENABLED", "true")
    reset_job_manager()

    class FakeProc:
        pid = 4242

        def wait(self, timeout=None):
            return 0

        @property
        def returncode(self):
            return 0

    mock_popen.return_value = FakeProc()
    mgr = MediaCrawlerJobManager()
    job = mgr.submit(
        CrawlJobRequest(platform="bili", crawl_type="search", keywords="AI", cookie="sess=1", dry_run=False)
    )
    assert job.status in {"completed", "running", "pending"}
    # 背景執行，稍等線程
    import time

    for _ in range(20):
        refreshed = mgr.get_job(job.job_id)
        assert refreshed is not None
        if refreshed.status in {"completed", "failed"}:
            break
        time.sleep(0.05)
    final = mgr.get_job(job.job_id)
    assert final is not None
    assert final.status == "completed"
    mock_popen.assert_called_once()


def test_safe_result_path_rejects_traversal(mediacrawler_env):
    from backend.mediacrawler.config import MediaCrawlerConfigError

    with pytest.raises(MediaCrawlerConfigError):
        safe_result_path("../evil", "data.json")


def test_integration_status_tier(mediacrawler_env):
    status = integration_status()
    assert status["installation"]["installed"] is True
    assert status["tier"] in {"available", "needsKey", "enabled"}


def test_mediacrawler_api_endpoints(mediacrawler_env):
    client = TestClient(app)
    status = client.get("/mediacrawler/status")
    assert status.status_code == 200
    body = status.json()
    assert body["installation"]["installed"] is True
    assert "legal_notice" in body

    validate = client.post(
        "/mediacrawler/jobs/validate",
        json={"platform": "xhs", "crawl_type": "search", "keywords": "旅遊", "dry_run": True},
    )
    assert validate.status_code == 200
    assert validate.json()["valid"] is True

    dry = client.post(
        "/mediacrawler/jobs",
        json={"platform": "wb", "crawl_type": "search", "keywords": "新聞", "dry_run": True},
    )
    assert dry.status_code == 200
    job_id = dry.json()["job_id"]
    detail = client.get(f"/mediacrawler/jobs/{job_id}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "completed"

    config = client.put("/mediacrawler/config", json={"cookie": "test_cookie_value"})
    assert config.status_code == 200
    assert config.json()["cookie_configured"] is True


def test_service_validate_and_start(mediacrawler_env):
    payload = validate_job(
        {"platform": "zhihu", "crawl_type": "detail", "post_ids": "12345", "dry_run": True}
    )
    assert payload["valid"] is True
    job = start_job(
        {"platform": "tieba", "crawl_type": "search", "keywords": "測試", "dry_run": True}
    )
    assert job["status"] == "completed"
    assert json.loads(mediacrawler_env["jobs_store"].read_text(encoding="utf-8"))["jobs"]
