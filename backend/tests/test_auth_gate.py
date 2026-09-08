"""閘門：覆寫環境身分後驗證登入／拒絕／受保護路由。"""

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def gated_app(monkeypatch):
    monkeypatch.setenv("LINKIN_AUTH_FORCE", "1")
    monkeypatch.setenv("LINKIN_GATE_ID", "alice")
    monkeypatch.setenv("LINKIN_GATE_SECRET", "s3cret-test")
    monkeypatch.delenv("LINKIN_AUTH_DISABLED", raising=False)
    from backend.main import app

    return app


def test_login_rejects_wrong_secret(gated_app):
    with TestClient(gated_app) as client:
        resp = client.post("/auth/login", json={"username": "alice", "password": "nope"})
        assert resp.status_code == 401
        assert client.get("/health").status_code == 200
        assert client.get("/dashboard").status_code == 401


def test_login_issues_session_and_unlocks(gated_app):
    with TestClient(gated_app) as client:
        resp = client.post("/auth/login", json={"username": "alice", "password": "s3cret-test"})
        assert resp.status_code == 200
        data = resp.json()
        token = data["token"]
        assert data["user"] == "alice"
        assert token

        # TestClient 會保存 Cookie，登入後同一客戶端應可進入
        via_cookie = client.get("/dashboard")
        assert via_cookie.status_code == 200

        me = client.get("/auth/me", headers={"X-Linkin-Gate": token})
        assert me.status_code == 200
        assert me.json()["user"] == "alice"

        client.post("/auth/logout", headers={"X-Linkin-Gate": token})
        after = client.get("/dashboard", headers={"X-Linkin-Gate": token})
        assert after.status_code == 401

    with TestClient(gated_app) as stranger:
        denied = stranger.get("/dashboard", headers={"X-Linkin-Gate": token})
        assert denied.status_code == 401


def test_header_unlocks_without_cookie(gated_app):
    with TestClient(gated_app) as issuer:
        token = issuer.post(
            "/auth/login", json={"username": "alice", "password": "s3cret-test"}
        ).json()["token"]

    with TestClient(gated_app) as client:
        denied = client.get("/dashboard")
        assert denied.status_code == 401
        ok = client.get("/dashboard", headers={"X-Linkin-Gate": token})
        assert ok.status_code == 200


def test_pytest_default_skips_gate():
    """一般單測不帶 LINKIN_AUTH_FORCE 時，既有 TestClient 不受阻。"""
    assert os.getenv("PYTEST_CURRENT_TEST")
    from backend.auth.gate import gate_enabled

    assert gate_enabled() is False


def test_default_digests_reject_garbage(monkeypatch):
    monkeypatch.setenv("LINKIN_AUTH_FORCE", "1")
    monkeypatch.delenv("LINKIN_GATE_ID", raising=False)
    monkeypatch.delenv("LINKIN_GATE_SECRET", raising=False)
    from backend.main import app

    with TestClient(app) as client:
        resp = client.post("/auth/login", json={"username": "nope", "password": "nope"})
        assert resp.status_code == 401


def test_default_digest_fragments_are_well_formed():
    from backend.auth import gate as g

    user_hex = "".join(g._U)
    secret_hex = "".join(g._S)
    assert len(g._U) == 4 and len(g._S) == 4
    assert len(user_hex) == 64 and len(secret_hex) == 64
    assert all(len(part) == 16 for part in (*g._U, *g._S))
    assert user_hex != secret_hex
    assert g._digest("nope") != user_hex
    assert g._digest("nope") != secret_hex


def test_frontend_gate_fragments_stay_in_sync():
    from pathlib import Path

    from backend.auth import gate as g

    src = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "gateDigest.ts"
    text = src.read_text(encoding="utf-8")
    for part in (*g._U, *g._S):
        assert part in text
