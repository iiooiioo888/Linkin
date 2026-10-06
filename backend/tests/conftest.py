"""pytest 設定：確保專案根目錄在 sys.path，使 backend 套件可被匯入。

另以 autouse fixture 將執行期資料寫入暫存位置，避免測試污染 repo 內
backend/data/、config 與其他可追蹤路徑。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

_EMPTY_ROUTING_FEEDBACK = {
    "records": [],
    "stats": {"simple": 0, "company": 0},
    "meta": {"consecutive_simple_low": 0},
}

_EMPTY_USER_FEEDBACK = {
    "records": [],
    "stats": {"thumbs_up": 0, "thumbs_down": 0, "copy": 0, "edit": 0},
}


def _git_porcelain() -> str | None:
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


@pytest.fixture(scope="session", autouse=True)
def _guard_tracked_files_unchanged():
    """整個測試 session 結束時，工作區相對於 session 開始不得新增變更。"""
    before = _git_porcelain()
    yield
    if before is None:
        return
    after = _git_porcelain()
    if after is None:
        return
    if after != before:
        pytest.fail(
            "測試 session 修改了 git 追蹤的工作區檔案。\n"
            f"session 開始：\n{before or '(clean)'}\n"
            f"session 結束：\n{after or '(clean)'}"
        )


@pytest.fixture(autouse=True)
def _isolate_archive_dir(tmp_path, monkeypatch):
    """所有測試共用：將 JSONL 存檔寫入暫存目錄。"""
    monkeypatch.setenv("EVOL_ARCHIVE_DIR", str(tmp_path / "archives"))
    yield


@pytest.fixture(autouse=True)
def _isolate_company_run_log_dir(tmp_path, monkeypatch):
    """所有測試共用：將公司執行軌跡 sink 寫入暫存目錄。"""
    monkeypatch.setenv("EVOL_COMPANY_RUN_LOG_DIR", str(tmp_path / "company_runs"))
    yield


@pytest.fixture(autouse=True)
def _isolate_trace_and_checkpoint_dirs(tmp_path, monkeypatch):
    """所有測試共用：將任務軌跡與檢查點寫入暫存，避免污染真實目錄。

    漏掉這個隔離時，走 `TestClient` 的端到端用例（如 /chat/stream、
    /tasks）會把 `trace_*.jsonl` 落到 repo 根目錄或 `backend/data/traces/`，
    造成工作區髒亂，並讓已被上游誤提交的根目錄 trace 持續被改写。
    """
    monkeypatch.setenv("EVOL_TRACE_DIR", str(tmp_path / "traces"))
    monkeypatch.setenv("EVOL_CHECKPOINT_DIR", str(tmp_path / "checkpoints"))
    yield


@pytest.fixture(autouse=True)
def _isolate_role_catalog(tmp_path, monkeypatch):
    """所有測試共用：角色目錄寫入暫存，避免污染真實 data/。"""
    monkeypatch.setenv("EVOL_ROLE_CATALOG_PATH", str(tmp_path / "role_catalog.json"))
    from backend.company.role_catalog import reset_catalog_cache

    reset_catalog_cache()
    yield
    reset_catalog_cache()


@pytest.fixture(autouse=True)
def _isolate_minecraft_mcp(tmp_path, monkeypatch):
    """所有測試共用：Minecraft MCP 預設乾跑，審計寫入暫存。"""
    monkeypatch.setenv("EVOL_MC_MCP_ENABLED", "false")
    monkeypatch.setenv("EVOL_MC_MCP_TOKEN", "")
    monkeypatch.setenv("EVOL_MC_MCP_AUDIT_PATH", str(tmp_path / "mcp_audit.jsonl"))
    yield


@pytest.fixture(autouse=True)
def _isolate_llm_config_and_ops(tmp_path, monkeypatch):
    """隔離 LLM 配置檔，並關閉模型目錄背景迴圈。"""
    monkeypatch.setenv("EVOL_CONFIG_DIR", str(tmp_path / "llm_cfg"))
    monkeypatch.setenv("EVOL_LLM_OPS_ENABLED", "false")
    # save_runtime_config 會寫入 process env；必須每測試清空以免污染 clamp_model
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    monkeypatch.delenv("EVOL_MODEL", raising=False)
    from backend.core.api_router import reset_router_state
    from backend.core.llm_config import reset_runtime_config
    from backend.core.provider_pool import reset_pool_health

    reset_runtime_config()
    reset_router_state()
    reset_pool_health()
    yield
    reset_runtime_config()
    reset_router_state()
    reset_pool_health()


@pytest.fixture(autouse=True)
def _isolate_routing_feedback(tmp_path, monkeypatch):
    """路由自適應反饋寫入暫存，避免污染 backend/data/routing_feedback.json。"""
    fb = tmp_path / "routing_feedback.json"
    fb.write_text(json.dumps(_EMPTY_ROUTING_FEEDBACK), encoding="utf-8")
    monkeypatch.setenv("EVOL_ROUTING_FEEDBACK_PATH", str(fb))
    from backend.core import routing_feedback

    routing_feedback._last_threshold_log = None
    yield
    routing_feedback._last_threshold_log = None


@pytest.fixture(autouse=True)
def _isolate_cost_speed_config(tmp_path, monkeypatch):
    """cost_speed 配置寫入暫存副本，避免 PUT API 改動 repo 內 JSON。"""
    from backend.core.cost_speed_router import reload_cost_speed

    src = BACKEND_ROOT / "config" / "cost_speed.json"
    dst = tmp_path / "cost_speed.json"
    if src.is_file():
        shutil.copy(src, dst)
    else:
        dst.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("EVOL_COST_SPEED_PATH", str(dst))
    reload_cost_speed()
    yield
    reload_cost_speed()


@pytest.fixture(autouse=True)
def _isolate_user_feedback(tmp_path, monkeypatch):
    """用戶反饋閉環寫入暫存。"""
    path = tmp_path / "user_feedback.json"
    path.write_text(json.dumps(_EMPTY_USER_FEEDBACK), encoding="utf-8")
    monkeypatch.setenv("EVOL_USER_FEEDBACK_PATH", str(path))
    yield


@pytest.fixture(autouse=True)
def _isolate_state_and_memory_stores(tmp_path, monkeypatch):
    """JSONL 狀態目錄、Chroma 持久化與 dashboard 記憶庫寫入暫存。"""
    monkeypatch.setenv("EVOL_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("EVOL_CHROMA_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("EVOL_MEMORY_STORE_PATH", str(tmp_path / "memory.json"))
    yield


@pytest.fixture(autouse=True)
def _isolate_linkin_runtime_data(tmp_path, monkeypatch):
    """靈境資料目錄與憲法路徑寫入暫存（憲法自 repo 唯讀複製）。"""
    linkin_dir = tmp_path / "linkin"
    linkin_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("EVOL_LINKIN_DATA_DIR", str(linkin_dir))
    monkeypatch.setenv("EVOL_LINKIN_CHROMA_DIR", str(tmp_path / "linkin_chroma"))
    const_dst = tmp_path / "linkin_constitution.json"
    const_src = BACKEND_ROOT / "data" / "linkin_constitution.json"
    if const_src.is_file():
        shutil.copy(const_src, const_dst)
    monkeypatch.setenv("EVOL_LINKIN_CONSTITUTION_PATH", str(const_dst))
    from backend.linkin.constitution import reset_cache

    reset_cache()
    yield
    reset_cache()


@pytest.fixture(autouse=True)
def _isolate_server_admin_paths(tmp_path, monkeypatch):
    """伺服器管理批准隊列、審計與備份寫入暫存。"""
    root = tmp_path / "server_admin"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("EVOL_SA_BACKUP_DIR", str(root / "backups"))
    monkeypatch.setenv("EVOL_SA_AUDIT_PATH", str(root / "server_audit.jsonl"))
    monkeypatch.setenv("EVOL_SA_PENDING_PATH", str(root / "server_pending.json"))
    yield


@pytest.fixture(autouse=True)
def _isolate_mediacrawler_data(tmp_path, monkeypatch):
    """MediaCrawler 結果、運行時配置與任務 store 寫入暫存。"""
    mc_root = tmp_path / "mediacrawler"
    mc_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("EVOL_MEDIACRAWLER_RESULTS_ROOT", str(mc_root / "results"))
    monkeypatch.setenv("EVOL_MEDIACRAWLER_CONFIG", str(mc_root / "runtime.json"))
    monkeypatch.setenv("EVOL_MEDIACRAWLER_JOBS_STORE", str(mc_root / "jobs.json"))
    monkeypatch.setenv("EVOL_MEDIACRAWLER_ENABLED", "false")
    yield
