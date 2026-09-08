"""服務器運維智能體（AIOps）測試：底層護欄、批准隊列、LLM/關鍵詞規劃、API。

全部 monkeypatch 隔離：無需真實 systemd/docker/LLM 金鑰（AGENTS.md 約束 #2）。
預設乾跑（EVOL_SA_ENABLED 未設）——寫操作只模擬不落盤。
"""

from __future__ import annotations

import gzip
import json
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.linkin import server_admin as server_ops
from backend.tools import server_admin as sa
from backend.tools.server_admin import ServerAdminError


@pytest.fixture()
def sa_env(tmp_path, monkeypatch):
    root = tmp_path / "mmorpg"
    for sub in ("packages", "temp", "logs", "assets", "schematics"):
        (root / sub).mkdir(parents=True)
    monkeypatch.setenv("EVOL_SA_STORAGE_ROOT", str(root))
    monkeypatch.setenv("EVOL_SA_BACKUP_DIR", str(root / "backups"))
    monkeypatch.setenv("EVOL_SA_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("EVOL_SA_PENDING_PATH", str(tmp_path / "pending.json"))
    monkeypatch.setenv("EVOL_SA_SERVICES", "linkin-api,mysql")
    monkeypatch.delenv("EVOL_SA_ENABLED", raising=False)
    monkeypatch.delenv("EVOL_SA_AUTO_APPROVE", raising=False)
    monkeypatch.setenv("EVOL_SA_NO_LLM", "true")  # 預設關鍵詞路由；LLM 測試單獨 monkeypatch
    server_ops.reset_cache()
    yield root
    server_ops.reset_cache()


@pytest.fixture()
def client(sa_env):
    from backend.linkin.api import register_linkin

    app = FastAPI()
    register_linkin(app)
    return TestClient(app)


def _make_file(path: Path, size: int = 16, age_days: float = 0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    if age_days:
        old = time.time() - age_days * 86400
        import os

        os.utime(path, (old, old))
    return path


def _audit_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# ══════════════ 底層橋接：配置與護欄 ══════════════


def test_config_dry_run_by_default(sa_env):
    cfg = sa.load_config()
    assert cfg.dry_run is True
    assert cfg.storage_root == sa_env
    assert cfg.allow_services == ("linkin-api", "mysql")


def test_config_enabled_switch(sa_env, monkeypatch):
    monkeypatch.setenv("EVOL_SA_ENABLED", "true")
    assert sa.load_config().dry_run is False


def test_unknown_tool_rejected(sa_env):
    with pytest.raises(ServerAdminError) as ei:
        sa.execute_named_tool("format_disk", {})
    assert ei.value.code == "unknown_tool"


def test_dangerous_input_backstop(sa_env):
    with pytest.raises(ServerAdminError) as ei:
        sa.execute_named_tool("get_disk_usage", {"target": "rm -rf /"})
    assert ei.value.code == "dangerous_input"
    with pytest.raises(ServerAdminError) as ei2:
        sa.execute_named_tool("restart_service", {"name": "mysql; rm -rf /"})
    assert ei2.value.code == "dangerous_input"


def test_path_traversal_denied(sa_env):
    with pytest.raises(ServerAdminError) as ei:
        sa.get_disk_usage("../../escape")
    assert ei.value.code == "path_denied"
    with pytest.raises(ServerAdminError) as ei2:
        sa._resolve_under_root(sa.load_config(), str(Path(sa_env).parent / "outside"))
    assert ei2.value.code == "path_denied"


# ══════════════ 底層橋接：讀操作 ══════════════


def test_disk_usage_real_metrics(sa_env):
    result = sa.get_disk_usage()
    assert result["ok"] is True
    assert result["total_gb"] > 0
    assert 0 <= result["percent"] <= 100
    assert result["path"] == str(sa_env.resolve())


def test_system_load_metrics(sa_env):
    result = sa.get_system_load()
    assert result["ok"] is True
    assert isinstance(result["cpu_percent"], float)
    assert 0 <= result["memory"]["percent"] <= 100
    mem = sa.get_memory_usage()
    assert mem["memory"]["percent"] == result["memory"]["percent"] or mem["ok"] is True


def test_docker_status_degrades_gracefully(sa_env):
    result = sa.get_docker_status()
    assert result["ok"] is True
    assert "available" in result
    if not result["available"]:
        assert result["reason"]


def test_check_service_allowlist(sa_env):
    with pytest.raises(ServerAdminError) as ei:
        sa.check_service("nginx")  # 不在 EVOL_SA_SERVICES 允許清單
    assert ei.value.code == "service_denied"
    with pytest.raises(ServerAdminError) as ei2:
        sa.check_service("bad;name")
    assert ei2.value.code == "invalid_service"
    result = sa.check_service("mysql")
    assert result["ok"] is True
    if result["available"]:
        assert result["active"] in {"active", "inactive", "failed", "unknown"}
    else:
        assert "systemctl" in result["reason"] or result["reason"]


def test_analyze_disk_growth(sa_env):
    _make_file(sa_env / "packages" / "big.zip", 2000)
    _make_file(sa_env / "logs" / "app.log", 500)
    _make_file(sa_env / "temp" / "old.tmp", 300, age_days=10)
    result = sa.analyze_disk_growth(days=7, top=5)
    assert result["ok"] is True
    assert result["scanned_files"] == 3
    assert result["by_directory"][0]["dir"] == "packages"
    growth_dirs = {r["dir"] for r in result["recent_growth"]}
    assert growth_dirs == {"packages", "logs"}  # 10 天前的 temp 不算近 7 天增長
    assert result["largest_recent"][0]["path"].endswith("big.zip")


def test_tail_log(sa_env, tmp_path):
    (sa_env / "logs" / "app.log").write_text("L1\nL2\nL3\nL4\nL5\n", encoding="utf-8")
    result = sa.tail_log("app.log", lines=3)
    assert result["ok"] is True
    assert result["lines"] == ["L3", "L4", "L5"]
    # 審計日誌本身可讀
    sa.get_disk_usage()
    audit = sa.tail_log("audit", lines=10)
    assert audit["ok"] is True and audit["line_count"] >= 1
    # 路徑穿越與非法名
    with pytest.raises(ServerAdminError) as ei:
        sa.tail_log("../secret.log")
    assert ei.value.code == "path_denied"
    with pytest.raises(ServerAdminError) as ei2:
        sa.tail_log("..")
    assert ei2.value.code == "path_denied"
    missing = sa.tail_log("nope.log")
    assert missing["ok"] is False


# ══════════════ 底層橋接：寫操作（confirm 矩陣）══════════════


def test_clean_packages_pending_preview(sa_env):
    _make_file(sa_env / "packages" / "old.zip", 100, age_days=10)
    _make_file(sa_env / "packages" / "new.zip", 100, age_days=1)
    result = sa.clean_old_packages(7, confirm=False)
    assert result["status"] == "pending_confirmation"
    assert result["count"] == 1
    assert (sa_env / "packages" / "old.zip").exists()  # 預覽無副作用


def test_clean_packages_dry_run_simulated(sa_env, tmp_path):
    old = _make_file(sa_env / "packages" / "old.zip", 100, age_days=10)
    result = sa.clean_old_packages(7, confirm=True)
    assert result["status"] == "simulated" and result["dry_run"] is True
    assert result["would_delete"] == 1 and result["would_free_bytes"] == 100
    assert old.exists()  # 乾跑不刪
    rows = _audit_rows(tmp_path / "audit.jsonl")
    assert any(r["tool"] == "clean_old_packages" and r["status"] == "simulated" and r["dry_run"] for r in rows)


def test_clean_packages_live_deletes(sa_env, tmp_path, monkeypatch):
    monkeypatch.setenv("EVOL_SA_ENABLED", "true")
    old = _make_file(sa_env / "packages" / "old.zip", 100, age_days=10)
    new = _make_file(sa_env / "packages" / "new.zip", 50, age_days=1)
    result = sa.clean_old_packages(7, confirm=True)
    assert result["status"] == "executed"
    assert result["deleted"] == 1 and result["freed_bytes"] == 100
    assert not old.exists()
    assert new.exists()
    rows = _audit_rows(tmp_path / "audit.jsonl")
    assert any(r["tool"] == "clean_old_packages" and r["status"] == "executed" and not r["dry_run"] for r in rows)


def test_clean_temp_live(sa_env, monkeypatch):
    monkeypatch.setenv("EVOL_SA_ENABLED", "true")
    old = _make_file(sa_env / "temp" / "cache.tmp", 30, age_days=5)
    fresh = _make_file(sa_env / "temp" / "now.tmp", 30)
    pending = sa.clean_temp_files(3, confirm=False)
    assert pending["status"] == "pending_confirmation" and pending["count"] == 1
    result = sa.clean_temp_files(3, confirm=True)
    assert result["deleted"] == 1
    assert not old.exists() and fresh.exists()


def test_rotate_logs_live(sa_env, monkeypatch):
    monkeypatch.setenv("EVOL_SA_ENABLED", "true")
    payload = b"log-line\n" * 150_000  # ~1.35MB
    log = sa_env / "logs" / "app.log"
    log.write_bytes(payload)
    pending = sa.rotate_logs(1, confirm=False)
    assert pending["status"] == "pending_confirmation" and pending["count"] == 1
    result = sa.rotate_logs(1, confirm=True)
    assert result["status"] == "executed" and result["rotated"] == 1
    assert log.stat().st_size == 0  # 原文件清空（保留 inode）
    archives = list((sa_env / "logs").glob("app.log.*.gz"))
    assert len(archives) == 1
    with gzip.open(archives[0], "rb") as fh:
        assert fh.read() == payload


def test_restart_service_guards_no_subprocess(sa_env, monkeypatch):
    with pytest.raises(ServerAdminError) as ei:
        sa.restart_service("nginx", confirm=True)  # 不在允許清單
    assert ei.value.code == "service_denied"

    pending = sa.restart_service("mysql", confirm=False)
    assert pending["status"] == "pending_confirmation"

    def _boom(*args, **kwargs):
        raise AssertionError("乾跑/無 systemctl 環境絕不可呼叫 subprocess")

    monkeypatch.setattr(sa.subprocess, "run", _boom)
    result = sa.restart_service("mysql", confirm=True)
    assert result["status"] in {"simulated", "unsupported"}
    assert result["ok"] is True


def test_restart_service_live_invokes_systemctl(sa_env, monkeypatch):
    monkeypatch.setenv("EVOL_SA_ENABLED", "true")
    monkeypatch.setattr(sa.shutil, "which", lambda name: "/usr/bin/systemctl")
    captured: dict = {}

    class _Proc:
        returncode = 0
        stdout = "restarted"
        stderr = ""

    def _fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["timeout"] = kwargs.get("timeout")
        return _Proc()

    monkeypatch.setattr(sa.subprocess, "run", _fake_run)
    result = sa.restart_service("mysql", confirm=True)
    assert result["status"] == "executed" and result["ok"] is True
    assert captured["argv"] == ["systemctl", "restart", "mysql"]  # argv 列表，無 shell=True
    assert captured["timeout"] == sa.SUBPROCESS_TIMEOUT


def test_backup_incremental_lifecycle(sa_env, monkeypatch):
    a = _make_file(sa_env / "assets" / "img" / "a.png", 64)
    _make_file(sa_env / "assets" / "b.png", 32)
    dry = sa.backup_incremental("assets", confirm=True)
    assert dry["status"] == "simulated" and dry["would_copy"] == 2

    monkeypatch.setenv("EVOL_SA_ENABLED", "true")
    first = sa.backup_incremental("assets", confirm=True)
    assert first["status"] == "executed" and first["copied"] == 2
    assert (sa_env / "backups" / "assets" / "img" / "a.png").exists()

    second = sa.backup_incremental("assets", confirm=True)
    assert second["copied"] == 0  # 增量：未變更跳過

    a.write_bytes(b"y" * 128)  # 改變大小與 mtime
    third = sa.backup_incremental("assets", confirm=True)
    assert third["copied"] == 1


def test_backup_path_denied(sa_env):
    with pytest.raises(ServerAdminError) as ei:
        sa.backup_incremental("../escape", confirm=True)
    assert ei.value.code == "path_denied"


# ══════════════ 域層：批准隊列 ══════════════


def test_execute_for_agent_creates_approval(sa_env):
    _make_file(sa_env / "packages" / "old.zip", 100, age_days=10)
    out = server_ops.execute_for_agent("clean_old_packages", {"days": 7}, role="custom_server_admin")
    assert out["status"] == "pending_approval"
    assert out["approval_id"].startswith("sa-")
    assert "ZIP" in out["message"] and "1 个" in out["message"]
    approvals = server_ops.list_approvals()
    assert len(approvals) == 1 and approvals[0]["status"] == "pending"


def test_confirm_approval_executes_and_blocks_reuse(sa_env):
    _make_file(sa_env / "packages" / "old.zip", 100, age_days=10)
    out = server_ops.execute_for_agent("clean_old_packages", {"days": 7})
    record = server_ops.confirm_approval(out["approval_id"])
    assert record["status"] == "executed"
    assert record["result"]["status"] == "simulated"  # 乾跑下的執行=模擬
    with pytest.raises(ServerAdminError) as ei:
        server_ops.confirm_approval(out["approval_id"])
    assert ei.value.code == "invalid_state"


def test_cancel_approval(sa_env):
    out = server_ops.execute_for_agent("clean_temp_files", {"days": 3})
    record = server_ops.cancel_approval(out["approval_id"])
    assert record["status"] == "cancelled"
    with pytest.raises(ServerAdminError):
        server_ops.confirm_approval(out["approval_id"])


def test_approval_expiry(sa_env):
    out = server_ops.execute_for_agent("clean_temp_files", {"days": 3})
    path = server_ops.pending_path()
    data = json.loads(path.read_text(encoding="utf-8"))
    data["approvals"][-1]["created_ts"] = time.time() - 7200  # 超過 TTL(30min)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    server_ops.reset_cache()
    with pytest.raises(ServerAdminError) as ei:
        server_ops.confirm_approval(out["approval_id"])
    assert ei.value.code == "expired"
    assert all(a["status"] != "pending" for a in server_ops.list_approvals())


def test_confirm_unknown_approval_404(sa_env):
    with pytest.raises(LookupError):
        server_ops.confirm_approval("sa-doesnotex")


# ══════════════ 域層：ask_agent（關鍵詞 + LLM）══════════════


def test_ask_keyword_disk_growth(sa_env):
    _make_file(sa_env / "packages" / "big.zip", 2000)
    out = server_ops.ask_agent("最近磁盤為什麼漲得這麼快？")
    assert out["status"] == "ok" and out["planner"] == "keyword"
    assert out["tool"] == "analyze_disk_growth"
    assert out["result"]["by_directory"][0]["dir"] == "packages"


def test_ask_keyword_restart_creates_approval(sa_env):
    out = server_ops.ask_agent("mysql 崩潰了，幫我重啟")
    assert out["status"] == "pending_approval"
    assert out["tool"] == "restart_service"
    assert out["params"] == {"name": "mysql"}
    assert out["approval_required"] is True
    assert out["proposed_action"]
    assert out["expires_in_min"] == 30


def test_ask_keyword_health_default(sa_env):
    out = server_ops.ask_agent("服務器最近感覺怪怪的")
    assert out["tool"] == "health"
    assert out["result"]["status"] in {"ok", "warn", "critical"}
    assert any(c["name"] == "disk" for c in out["result"]["checks"])


def test_ask_patrol_route(sa_env):
    out = server_ops.ask_agent("對服務器做一次全面巡檢")
    assert out["tool"] == "patrol"
    assert "snapshot" in out["result"] and "proposals" in out["result"]


def test_ask_llm_plan_sanitizes_params(sa_env, monkeypatch):
    monkeypatch.setenv("EVOL_SA_NO_LLM", "false")
    monkeypatch.setattr(server_ops, "_llm_ready", lambda: True)
    monkeypatch.setattr(
        server_ops,
        "call_llm",
        lambda prompt, system="", model=None, **kw: json.dumps(
            {"tool": "clean_temp_files", "params": {"days": "5", "evil": "rm -rf /", "x": 1}, "analysis": "清理臨時文件"},
            ensure_ascii=False,
        ),
    )
    out = server_ops.ask_agent("幫我清理臨時目錄")
    assert out["planner"] == "llm"
    assert out["tool"] == "clean_temp_files"
    assert out["params"] == {"days": 5}  # 幻覺參數丟棄、"5" 收斂為 int
    assert out["status"] == "pending_approval"


def test_ask_llm_garbage_falls_back_to_keyword(sa_env, monkeypatch):
    monkeypatch.setattr(server_ops, "_llm_ready", lambda: True)
    monkeypatch.setattr(server_ops, "call_llm", lambda *a, **kw: "抱歉，我无法输出 JSON。")
    out = server_ops.ask_agent("帮我看看应用日誌")
    assert out["planner"] == "keyword"
    assert out["tool"] == "tail_log"


def test_ask_llm_error_falls_back(sa_env, monkeypatch):
    monkeypatch.setattr(server_ops, "_llm_ready", lambda: True)

    def _boom(*a, **kw):
        raise RuntimeError("LLM 服務不可用")

    monkeypatch.setattr(server_ops, "call_llm", _boom)
    out = server_ops.ask_agent("看看 docker 容器狀態")
    assert out["planner"] == "keyword" and out["tool"] == "get_docker_status"


def test_ask_auto_approve_requires_double_opt_in(sa_env, monkeypatch):
    _make_file(sa_env / "packages" / "old.zip", 100, age_days=10)
    out = server_ops.ask_agent("清理舊 zip 包", auto_approve=True)
    assert out["status"] == "pending_approval"  # 僅 API 參數不夠，需環境雙開關

    monkeypatch.setenv("EVOL_SA_AUTO_APPROVE", "true")
    out2 = server_ops.ask_agent("清理舊 zip 包", auto_approve=True)
    assert out2["status"] == "executed" and out2["auto_approved"] is True
    assert out2["result"]["status"] == "simulated"  # 乾跑下仍是模擬


def test_ask_empty_question(sa_env):
    with pytest.raises(ValueError):
        server_ops.ask_agent("   ")


# ══════════════ 域層：巡檢 / 日報 / 審計 ══════════════


def test_health_snapshot_structure(sa_env):
    snapshot = server_ops.health_snapshot()
    assert snapshot["status"] in {"ok", "warn", "critical"}
    names = [c["name"] for c in snapshot["checks"]]
    assert "disk" in names and "system" in names and "docker" in names
    assert "service:mysql" in names


def test_patrol_proposes_restart_for_failed_service(sa_env, monkeypatch):
    def _fake_check(name, *, config=None):
        return {"ok": True, "available": True, "service": name, "active": "failed" if name == "mysql" else "active"}

    monkeypatch.setattr(server_ops.sa, "check_service", _fake_check)
    report = server_ops.patrol()
    assert report["snapshot"]["status"] == "critical"
    restarts = [p for p in report["proposals"] if p["tool"] == "restart_service"]
    assert restarts and restarts[0]["params"] == {"name": "mysql"}
    assert restarts[0]["action"] == "pending_approval"
    assert restarts[0]["approval_id"].startswith("sa-")
    assert any(a["tool"] == "restart_service" for a in server_ops.list_approvals())


def test_daily_report(sa_env):
    sa.get_disk_usage()
    server_ops.execute_for_agent("clean_temp_files", {"days": 3})
    report = server_ops.daily_report()
    assert "服務器日報" in report
    assert "disk:" in report
    assert "待批准操作：1 項" in report


def test_audit_tail(sa_env):
    sa.get_disk_usage()
    sa.get_system_load()
    rows = server_ops.audit_tail(10)
    assert len(rows) >= 2
    assert all({"ts", "tool", "dry_run"} <= set(r) for r in rows)


# ══════════════ 公司整合：工具註冊表 + 角色預設 ══════════════


def test_company_registry_server_tools(sa_env):
    from backend.company.tools import tool_registry

    write = tool_registry.get("server_restart_service")
    assert write is not None and write.readonly is False
    assert "devops" in write.allowed_roles and "server_admin" in write.allowed_roles
    assert tool_registry._role_matches("custom_server_admin", write.allowed_roles)

    read = tool_registry.get("server_disk_usage")
    assert read is not None and read.readonly is True and read.allowed_roles == []

    visible = {t.name for t in tool_registry.list_tools(role="story_writer")}
    assert "server_disk_usage" in visible  # 只讀開放
    assert "server_restart_service" not in visible  # 寫操作限維運角色


def test_company_registry_write_tool_routes_to_approval(sa_env):
    from backend.company.tools import tool_registry

    _make_file(sa_env / "packages" / "old.zip", 100, age_days=10)
    tool = tool_registry.get("server_clean_packages")
    out = tool.execute(days=7)  # 未帶 confirmed → 自動轉批准隊列
    assert out["status"] == "pending_approval"
    confirmed = tool.execute(days=7, confirmed=True)
    assert confirmed["status"] == "simulated" and confirmed["ok"] is True


def test_role_preset_registered(sa_env):
    from backend.company.role_catalog import _role_presets

    presets = {p["id"]: p for p in _role_presets()}
    preset = presets.get("server_admin")
    assert preset is not None
    assert preset["level"] == 4 and preset["category"] == "devops"
    assert preset["reporting_to"] == "tech_lead"
    assert preset["preferred_model"] == "qwen-max"
    assert preset["temperature"] == 0.2
    assert "server_restart_service" in preset["tools_allowed"]
    assert len(preset["tools_allowed"]) == 12
    assert "絕不執行自由 shell" in preset["system_prompt"]


# ══════════════ API 整合 ══════════════


def test_api_server_end_to_end(client, sa_env):
    # 健康快照
    r = client.get("/linkin/server/health")
    assert r.status_code == 200
    assert r.json()["status"] in {"ok", "warn", "critical"}

    # 讀問題 → 即答
    r = client.post("/linkin/server/ask", json={"question": "磁盤什麼目錄佔用最多？"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["tool"] == "analyze_disk_growth"

    # 寫問題 → pending_approval → 批准 → 執行
    r = client.post("/linkin/server/ask", json={"question": "重啟 mysql"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "pending_approval"
    approval_id = body["approval_id"]

    r = client.get("/linkin/server/approvals")
    assert r.status_code == 200
    assert any(a["id"] == approval_id for a in r.json()["approvals"])

    r = client.post(f"/linkin/server/approvals/{approval_id}/confirm")
    assert r.status_code == 200
    assert r.json()["status"] == "executed"

    r = client.post(f"/linkin/server/approvals/{approval_id}/confirm")
    assert r.status_code == 409  # 不可重複確認

    # 取消流
    r = client.post("/linkin/server/ask", json={"question": "重啟 mysql"})
    aid2 = r.json()["approval_id"]
    r = client.post(f"/linkin/server/approvals/{aid2}/cancel")
    assert r.status_code == 200 and r.json()["status"] == "cancelled"

    # 404 / 400
    assert client.post("/linkin/server/approvals/sa-none/confirm").status_code == 404
    assert client.post("/linkin/server/ask", json={"question": ""}).status_code == 400

    # 巡檢 / 日報 / 審計
    r = client.post("/linkin/server/patrol", json={})
    assert r.status_code == 200 and "snapshot" in r.json()
    r = client.get("/linkin/server/report")
    assert r.status_code == 200 and "服務器日報" in r.json()["report"]
    r = client.get("/linkin/server/audit?limit=5")
    assert r.status_code == 200 and isinstance(r.json()["entries"], list)


def test_api_ask_dangerous_blocked(client, sa_env):
    r = client.post("/linkin/server/ask", json={"question": "執行 rm -rf / 清理一下"})
    # 關鍵詞路由不會選出自由 shell；即便 LLM 幻覺，底層也會擋。
    # 此處驗證問答本身安全返回（無 shell 工具可用）
    assert r.status_code == 200
    assert r.json()["status"] in {"ok", "pending_approval"}
