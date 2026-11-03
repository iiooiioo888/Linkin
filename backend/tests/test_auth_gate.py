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


def _session_cookie(resp) -> str:
    token = resp.cookies.get("evoloop_gate")
    assert token
    return token


def test_login_issues_session_and_unlocks(gated_app):
    with TestClient(gated_app) as client:
        resp = client.post("/auth/login", json={"username": "alice", "password": "s3cret-test"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["user"] == "alice"
        assert "token" not in data
        token = _session_cookie(resp)
        cookie = resp.headers.get("set-cookie", "")
        assert "httponly" in cookie.lower()
        assert "samesite=lax" in cookie.lower()

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
        resp = issuer.post(
            "/auth/login", json={"username": "alice", "password": "s3cret-test"}
        )
        token = _session_cookie(resp)

    with TestClient(gated_app) as client:
        denied = client.get("/dashboard")
        assert denied.status_code == 401
        ok = client.get("/dashboard", headers={"X-Linkin-Gate": token})
        assert ok.status_code == 200


def test_query_token_does_not_authenticate(gated_app):
    with TestClient(gated_app) as issuer:
        resp = issuer.post(
            "/auth/login", json={"username": "alice", "password": "s3cret-test"}
        )
        token = _session_cookie(resp)

    with TestClient(gated_app) as client:
        denied = client.get("/dashboard", params={"gate": token})
        assert denied.status_code == 401


def test_pytest_default_skips_gate():
    """一般單測不帶 LINKIN_AUTH_FORCE 時，既有 TestClient 不受阻。"""
    assert os.getenv("PYTEST_CURRENT_TEST")
    from backend.auth.gate import gate_enabled

    assert gate_enabled() is False


def test_unset_gate_secrets_reject_login(monkeypatch):
    monkeypatch.setenv("LINKIN_AUTH_FORCE", "1")
    monkeypatch.delenv("LINKIN_GATE_ID", raising=False)
    monkeypatch.delenv("LINKIN_GATE_SECRET", raising=False)
    from backend.main import app

    with TestClient(app) as client:
        resp = client.post("/auth/login", json={"username": "alice", "password": "s3cret-test"})
        assert resp.status_code == 401


def test_openapi_is_not_anonymous(gated_app):
    with TestClient(gated_app) as client:
        assert client.get("/openapi.json").status_code in {401, 404}
        assert client.get("/docs").status_code in {401, 404}
        assert client.get("/redoc").status_code in {401, 404}


def test_path_counts_not_blocked_by_authgate(gated_app, monkeypatch):
    """AuthGate 放行 path-counts；無會話不得 401，交由 L2 閘回 403／200。"""
    monkeypatch.delenv("MODELGW_PATH_COUNTS_TOKEN", raising=False)
    monkeypatch.delenv("MODELGW_PATH_COUNTS_ALLOW_PRIVATE", raising=False)
    with TestClient(gated_app) as client:
        # 未登入：不得被 AuthGate 擋成 401；TestClient host 非 IP → L2 需 token → 403
        resp = client.get("/api/internal/modelgw/path-counts")
        assert resp.status_code == 403, resp.text
        assert resp.json().get("code") == "PATH_COUNTS_FORBIDDEN"


def test_path_counts_allowed_with_internal_token_without_session(gated_app, monkeypatch):
    """允許客戶端（正確內部 token）可過 AuthGate 抵達 handler → 200。"""
    monkeypatch.setenv("MODELGW_PATH_COUNTS_TOKEN", "secret-l2-authgate")
    with TestClient(gated_app) as client:
        denied = client.get("/api/internal/modelgw/path-counts")
        assert denied.status_code == 403
        ok = client.get(
            "/api/internal/modelgw/path-counts",
            headers={"X-ModelGW-Internal-Token": "secret-l2-authgate"},
        )
        assert ok.status_code == 200, ok.text
        body = ok.json()
        assert "via" in body and "would_block" in body and "bypass" in body
        assert body.get("hub_metrics_is_not_path_counts") is True

