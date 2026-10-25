"""每個登入帳號的設定隔離。

A 的 API 金鑰、整合開關、實驗室開關、採集 cookie、公司後反思覆寫
不得出現在 B 的讀取結果。未登入寫入在閘門開啟時拒絕。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.core.llm_config import get_runtime_config, reset_runtime_config, save_runtime_config
from backend.main import app
from backend.tenant.context import tenant_user_id


def _override(user: str) -> dict[str, str]:
    return {"X-Linkin-Tenant-Override": user}


def test_authenticated_user_does_not_inherit_platform_secret(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-platform-env-should-not-leak")
    monkeypatch.setenv("OPENAI_API_BASE", "https://platform.example/v1")
    save_runtime_config(
        api_key="sk-PLATFORM-FILE-KEY",
        api_base="https://api.deepseek.com",
        model="deepseek-v4-flash",
    )
    platform = get_runtime_config()
    assert platform["api_key"] == "sk-PLATFORM-FILE-KEY"

    token = tenant_user_id.set("bob")
    try:
        cfg = get_runtime_config()
    finally:
        tenant_user_id.reset(token)
    assert cfg.get("api_key") in ("", None)
    assert "sk-PLATFORM" not in json.dumps(cfg)
    assert "sk-platform-env" not in json.dumps(cfg)
    assert "platform.example" not in json.dumps(cfg)


def test_two_users_http_api_settings_do_not_leak(monkeypatch):
    monkeypatch.setattr(
        "backend.core.provider_pool._http_get_json",
        lambda url, key, timeout=15.0: {"data": [{"id": "qwen-plus"}]},
    )
    platform_path = Path(os.environ["EVOL_CONFIG_DIR"]) / "llm_config.json"
    with TestClient(app) as client:
        saved = client.post(
            "/config/routes",
            headers=_override("alice"),
            json={
                "id": "aliceqwen",
                "provider": "qwen",
                "name": "Alice Qwen",
                "api_key": "sk-ALICE-KEY-9999",
                "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "model": "qwen-plus",
                "is_default": True,
            },
        )
        assert saved.status_code == 200, saved.text
        alice = client.get("/config", headers=_override("alice"))
        bob = client.get("/config", headers=_override("bob"))
    assert alice.status_code == 200
    assert bob.status_code == 200
    alice_body = alice.json()
    bob_body = bob.json()
    assert alice_body["settings_user"] == "alice"
    assert bob_body["settings_user"] == "bob"
    assert "sk-ALICE-KEY-9999" not in alice.text
    assert "sk-ALICE-KEY-9999" not in bob.text
    assert any(route["id"] == "aliceqwen" for route in alice_body["api_routes"])
    assert all(route["id"] != "aliceqwen" for route in bob_body.get("api_routes") or [])
    assert "ALIC" not in bob.text
    blob = platform_path.read_text(encoding="utf-8") if platform_path.is_file() else ""
    assert "sk-ALICE-KEY-9999" not in blob


def test_two_real_logins_do_not_share_api_keys(monkeypatch):
    monkeypatch.setenv("LINKIN_AUTH_FORCE", "1")
    monkeypatch.setenv("LINKIN_GATE_ID", "gate-owner")
    monkeypatch.setenv("LINKIN_GATE_SECRET", "gate-secret")
    monkeypatch.setenv(
        "LINKIN_GATE_ACCOUNTS",
        json.dumps(
            [
                {"username": "alice", "secret": "secret-alice"},
                {"username": "bob", "secret": "secret-bob"},
            ]
        ),
    )
    monkeypatch.setattr(
        "backend.core.provider_pool._http_get_json",
        lambda url, key, timeout=15.0: {"data": [{"id": "deepseek-v4-flash"}]},
    )
    from backend.auth.gate import clear_failures

    clear_failures("testclient")
    with TestClient(app) as client:
        denied = client.post(
            "/config",
            json={"api_key": "sk-SHOULD-NOT-WRITE", "api_base": "https://api.deepseek.com", "model": "deepseek-v4-flash"},
        )
        assert denied.status_code == 401
        login_a = client.post("/auth/login", json={"username": "alice", "password": "secret-alice"})
        login_b = client.post("/auth/login", json={"username": "bob", "password": "secret-bob"})
        assert login_a.status_code == 200, login_a.text
        assert login_b.status_code == 200, login_b.text
        headers_a = {"X-Linkin-Gate": login_a.json()["token"]}
        headers_b = {"X-Linkin-Gate": login_b.json()["token"]}
        saved = client.post(
            "/config",
            headers=headers_a,
            json={
                "api_key": "sk-ALICE-LOGIN-KEY",
                "api_base": "https://api.deepseek.com",
                "model": "deepseek-v4-flash",
            },
        )
        assert saved.status_code == 200, saved.text
        assert "sk-ALICE-LOGIN-KEY" not in saved.text
        bob = client.get("/config", headers=headers_b)
        assert bob.status_code == 200
        assert bob.json()["settings_user"] == "bob"
        assert bob.json()["configured"] is False
        assert "sk-ALICE-LOGIN-KEY" not in bob.text
        assert "ALIC" not in bob.text


def test_integration_toggle_and_key_are_per_user():
    from backend.integrations.api import get_registry, reset_registry

    reset_registry()
    for client in get_registry().values():
        client.http.transport = lambda *_a, **_k: (200, b'{"ok":true}')
    with TestClient(app) as client:
        toggled = client.post(
            "/integrations/memos/toggle",
            headers=_override("alice"),
            json={"enabled": True},
        )
        assert toggled.status_code == 200
        assert toggled.json()["enabled"] is True
        saved = client.put(
            "/integrations/memos/settings",
            headers=_override("alice"),
            json={"base_url": "http://alice-memos.internal", "api_key": "memos-alice-secret"},
        )
        assert saved.status_code == 200, saved.text
        assert "memos-alice-secret" not in saved.text
        alice = client.get("/integrations", headers=_override("alice")).json()["integrations"]
        bob = client.get("/integrations", headers=_override("bob")).json()["integrations"]
    alice_memos = next(row for row in alice if row["name"] == "memos")
    bob_memos = next(row for row in bob if row["name"] == "memos")
    assert alice_memos["enabled"] is True
    assert alice_memos["base_url"] == "http://alice-memos.internal"
    assert alice_memos["has_api_key"] is True
    assert bob_memos["enabled"] is False
    assert bob_memos["base_url"] != "http://alice-memos.internal"
    assert bob_memos["has_api_key"] is False
    reset_registry()


def test_lab_memory_cookie_and_reflect_are_per_user():
    from backend.memory.json_store import JsonMemoryStore
    from backend.memory.tenant_store import collection_name_for

    assert collection_name_for("alice") != collection_name_for("bob")
    assert "bob" not in collection_name_for("alice")

    token = tenant_user_id.set("alice")
    try:
        JsonMemoryStore().add_memory("alice-only-memory")
    finally:
        tenant_user_id.reset(token)
    token = tenant_user_id.set("bob")
    try:
        assert JsonMemoryStore().all() == []
    finally:
        tenant_user_id.reset(token)

    with TestClient(app) as client:
        lab = client.put(
            "/config/lab",
            headers=_override("alice"),
            json={"mcp_tools": {"docker.inspect": True, "opc.read": False}},
        )
        assert lab.status_code == 200, lab.text
        assert lab.json()["mcp_tools"]["docker.inspect"] is True
        bob_lab = client.get("/config/lab", headers=_override("bob"))
        assert bob_lab.json()["mcp_tools"]["docker.inspect"] is False
        assert bob_lab.json()["mcp_tools"]["opc.read"] is True

        cookie = client.put(
            "/mediacrawler/config",
            headers=_override("alice"),
            json={"cookie": "alice-cookie-secret"},
        )
        assert cookie.status_code == 200
        assert cookie.json()["cookie_configured"] is True
        assert "alice-cookie-secret" not in cookie.text
        bob_cookie = client.get("/mediacrawler/config", headers=_override("bob"))
        assert bob_cookie.json()["cookie_configured"] is False
        assert "alice-cookie" not in bob_cookie.text

        reflect = client.put(
            "/config/cost-speed/post-company-reflect",
            headers=_override("alice"),
            json={"mode": "full"},
        )
        assert reflect.status_code == 200, reflect.text
        assert reflect.json()["user_override"] == "full"
        bob_reflect = client.get(
            "/config/cost-speed/post-company-reflect",
            headers=_override("bob"),
        )
        assert bob_reflect.json()["user_override"] is None
        assert bob_reflect.json()["source"] != "user"


def test_legacy_llm_config_copied_to_owner_only(tmp_path, monkeypatch):
    from backend.core.user_settings import migrate_legacy_user_settings

    cfg_dir = tmp_path / "platform_llm"
    cfg_dir.mkdir()
    legacy = cfg_dir / "llm_config.json"
    legacy.write_text(
        json.dumps({"api_key": "sk-LEGACY-OWNER-KEY", "api_base": "https://api.deepseek.com", "model": "deepseek-v4-flash"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("EVOL_CONFIG_DIR", str(cfg_dir))
    monkeypatch.setenv("EVOL_SETTINGS_LEGACY_OWNER", "ops_admin")
    monkeypatch.delenv("LINKIN_GATE_ID", raising=False)
    reset_runtime_config()
    report = migrate_legacy_user_settings(force=True)
    assert report["owner"] == "ops_admin"
    assert report["llm_copied"] is True
    assert legacy.is_file()
    assert "sk-LEGACY-OWNER-KEY" in legacy.read_text(encoding="utf-8")
    reset_runtime_config()

    token = tenant_user_id.set("ops_admin")
    try:
        owned = get_runtime_config()
    finally:
        tenant_user_id.reset(token)
    assert owned["api_key"] == "sk-LEGACY-OWNER-KEY"

    token = tenant_user_id.set("stranger")
    try:
        other = get_runtime_config()
    finally:
        tenant_user_id.reset(token)
    assert other.get("api_key") in ("", None)
    assert "sk-LEGACY" not in json.dumps(other)


def test_user_save_does_not_sync_process_env(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    token = tenant_user_id.set("alice")
    try:
        save_runtime_config(api_key="sk-ALICE-ENV-LEAK", api_base="https://api.deepseek.com", model="deepseek-v4-flash")
        assert get_runtime_config()["api_key"] == "sk-ALICE-ENV-LEAK"
    finally:
        tenant_user_id.reset(token)
    assert os.environ.get("OPENAI_API_KEY", "") != "sk-ALICE-ENV-LEAK"
    assert get_runtime_config().get("api_key") in ("", None)


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("POST", "/config", {"api_key": "sk-x", "api_base": "https://api.deepseek.com", "model": "deepseek-v4-flash"}),
        ("PUT", "/config/lab", {"mcp_tools": {"opc.read": False}}),
        ("POST", "/integrations/memos/toggle", {"enabled": True}),
        ("PUT", "/config/ops", {"refresh_interval_sec": 120}),
    ],
)
def test_gate_rejects_unauthenticated_settings_writes(monkeypatch, method, path, body):
    monkeypatch.setenv("LINKIN_AUTH_FORCE", "1")
    monkeypatch.setenv("LINKIN_GATE_ID", "alice")
    monkeypatch.setenv("LINKIN_GATE_SECRET", "secret-alice")
    with TestClient(app) as client:
        resp = client.request(method, path, json=body)
    assert resp.status_code == 401
