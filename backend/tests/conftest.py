"""pytest 設定：確保專案根目錄在 sys.path，使 backend 套件可被匯入。

另以 autouse fixture 將 Task 8.6 的存檔目錄隔離至暫存
位置，避免測試污染真實 data/ 目錄。
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


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
