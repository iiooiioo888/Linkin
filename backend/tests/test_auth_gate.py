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


def _restore(codes: list[int]) -> str:
    return "".join(chr(c ^ (0x5A + (i % 7))) for i, c in enumerate(codes))


def test_default_credentials_unlock(monkeypatch):
    """預設摘要對可解鎖（來源值不以明文寫在測試裡）。"""
    monkeypatch.setenv("LINKIN_AUTH_FORCE", "1")
    monkeypatch.delenv("LINKIN_GATE_ID", raising=False)
    monkeypatch.delenv("LINKIN_GATE_SECRET", raising=False)
    from backend.auth import gate as g
    from backend.main import app

    gate_id = _restore([51, 62, 51, 51, 57])
    gate_secret = _restore([22, 29, 20, 29, 14, 62, 68, 126, 44, 108, 47, 58])
    assert "$" in gate_secret
    assert g._digest(gate_id) == "".join(g._U)
    assert g._digest(gate_secret) == "".join(g._S)
    compact = gate_secret.replace("$$", "$")
    assert compact != gate_secret
    assert g._digest(compact) == "".join(g._S1)
    assert g._digest(gate_secret.replace("$", "")) != "".join(g._S)

    token = g.issue_login(gate_id, gate_secret, identity="unit")
    assert token
    assert g.session_user(token) == gate_id
    assert g.issue_login(gate_id, compact, identity="unit-compact")
    assert g.issue_login(gate_id, "wrong", identity="unit-bad") is None

    with TestClient(app) as client:
        resp = client.post(
            "/auth/login", json={"username": gate_id, "password": gate_secret}
        )
        assert resp.status_code == 200
        assert resp.json()["user"] == gate_id
        assert client.get("/dashboard").status_code == 200

    with TestClient(app) as client:
        resp = client.post(
            "/auth/login", json={"username": gate_id, "password": compact}
        )
        assert resp.status_code == 200


def test_frontend_gate_fragments_stay_in_sync():
    from pathlib import Path

    from backend.auth import gate as g

    src = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "gateDigest.ts"
    text = src.read_text(encoding="utf-8")
    for part in (*g._U, *g._S, *g._S1):
        assert part in text
    assert "ID_PARTS" in text
    assert "SECRET_PARTS" in text
    assert "matchPeeled" in text


def test_frontend_peel_unlocks_same_secret():
    """前端分段還原與後端摘要對同一組來源。"""
    from backend.auth import gate as g

    gate_id = _restore([51, 62, 51, 51, 57])
    gate_secret = _restore([22, 29, 20, 29, 14, 62, 68, 126, 44, 108, 47, 58])
    compact = gate_secret.replace("$$", "$")
    assert g._digest(gate_id) == "".join(g._U)
    assert g._digest(gate_secret) == "".join(g._S)
    assert g._digest(compact) == "".join(g._S1)
