"""Media Vault：入庫、縮圖、列表／監控 API、MediaCrawler 完成 hook。"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.main import app
from backend.media_vault import db as vault_db
from backend.media_vault.ingest import ingest_job_results
from backend.mediacrawler.config import CrawlJobRequest
from backend.mediacrawler.jobs import MediaCrawlerJobManager, reset_job_manager


@pytest.fixture()
def vault_env(tmp_path, monkeypatch):
    db_path = tmp_path / "vault.sqlite3"
    media_root = tmp_path / "media"
    monkeypatch.setenv("MEDIA_VAULT_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("MEDIA_VAULT_MEDIA_ROOT", str(media_root))
    vault_db.reset_media_vault_db()
    yield {"db": db_path, "media": media_root}
    vault_db.reset_media_vault_db()


def _make_image(path: Path, size=(640, 480)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color=(120, 80, 200)).save(path, format="JPEG")


def test_ingest_creates_thumbs_and_lists(vault_env):
    job_id = "job001"
    results = vault_env["media"].parent / "results" / job_id
    img = results / "photo.jpg"
    _make_image(img)
    manifest = [
        {
            "platform": "xhs",
            "source_url": "https://example.com/n/1",
            "user_name": "alice",
            "title": "測試帖",
            "image_list": ["photo.jpg"],
        }
    ]
    (results / "notes.json").write_text(json.dumps(manifest), encoding="utf-8")

    stats = ingest_job_results(job_id, results, platform="xhs", crawl_method="search")
    assert stats["ingested"] == 1
    assert stats["errors"] == []

    thumbs = list((vault_env["media"] / "thumbs").glob("*thumb_300*"))
    assert len(thumbs) >= 1

    client = TestClient(app)
    resp = client.get("/media-vault/images?platform=xhs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["author"] == "alice"
    assert item["risk_level"] == "green"

    detail = client.get(f"/media-vault/images/{item['id']}")
    assert detail.status_code == 200
    assets = detail.json()["assets"]
    kinds = {a["kind"] for a in assets}
    assert "original" in kinds
    assert "thumb_300" in kinds
    assert "thumb_800" in kinds

    asset_id = next(a["id"] for a in assets if a["kind"] == "thumb_300")
    file_resp = client.get(f"/media-vault/files/{asset_id}")
    assert file_resp.status_code == 200
    assert file_resp.headers["content-type"].startswith("image/")


def test_monitor_summary(vault_env):
    ingest_job_results("b2", vault_env["media"].parent / "empty", platform="dy")
    client = TestClient(app)
    summary = client.get("/media-vault/monitor/summary")
    assert summary.status_code == 200
    data = summary.json()
    assert "today_ingested" in data
    assert "compliance_distribution" in data


@pytest.fixture()
def mediacrawler_env(tmp_path, monkeypatch):
    home = tmp_path / "MediaCrawler"
    home.mkdir(exist_ok=True)
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
    yield
    reset_job_manager()


def test_mediacrawler_completion_triggers_ingest(mediacrawler_env, vault_env, monkeypatch):
    monkeypatch.setenv("EVOL_MEDIACRAWLER_ENABLED", "true")
    reset_job_manager()

    captured: list[tuple] = []

    def _fake_ingest(job_id, results_dir, **kwargs):
        captured.append((job_id, results_dir, kwargs))
        return {"ingested": 0, "errors": []}

    with patch("backend.media_vault.ingest.ingest_job_results", side_effect=_fake_ingest):
        with patch("backend.mediacrawler.jobs.subprocess.Popen") as mock_popen:

            class FakeProc:
                pid = 1

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
            import time

            for _ in range(30):
                refreshed = mgr.get_job(job.job_id)
                assert refreshed is not None
                if refreshed.status in {"completed", "failed"}:
                    break
                time.sleep(0.05)
            assert mgr.get_job(job.job_id).status == "completed"
            assert captured, "ingest should run after job completion"
