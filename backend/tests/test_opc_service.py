"""Phase 7：OPC 服務單元測試。

驗證：
1. 安全護欄（白名單檢查、邊界檢查）
2. 審計日誌寫入
3. 模擬 OPC 伺服器啟動與標籤讀寫
4. API 端點（健康檢查、標籤列表）
5. 閉環情境（異常檢測 → 診斷 → 控制動作）
"""

import asyncio
import json
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# 预先 mock asyncua 模块，避免测试环境缺少该依赖时导入失败
_mock_asyncua = MagicMock()
_mock_asyncua_ua = MagicMock()
_mock_asyncua_sub = MagicMock()
sys.modules.setdefault("asyncua", _mock_asyncua)
sys.modules.setdefault("asyncua.ua", _mock_asyncua_ua)
sys.modules.setdefault(
    "asyncua.common.subscription", _mock_asyncua_sub
)


# ---- 安全護欄測試 ----

def test_whitelist_allows_configured_prefix(monkeypatch):
    """白名單檢查：設定前綴後，匹配的標籤通過。"""
    monkeypatch.setenv("OPC_WRITE_WHITELIST", "Temperature,Pressure")
    from opc_service.config import OPCSettings

    settings = OPCSettings()
    from opc_service.guard import WriteGuard

    guard = WriteGuard()
    # 覆蓋設定
    monkeypatch.setattr(
        "opc_service.guard.settings", settings
    )

    ok, _ = guard.check_whitelist("Temperature")
    assert ok is True

    ok, _ = guard.check_whitelist("FlowRate")
    assert ok is False


def test_bounds_rejects_out_of_range():
    """邊界檢查：超出安全範圍的值被拒絕。"""
    from opc_service.guard import WriteGuard

    guard = WriteGuard()

    ok, msg = guard.check_bounds("Temperature", 25.0)
    assert ok is True

    ok, msg = guard.check_bounds("Temperature", 200.0)
    assert ok is False
    assert "超出" in msg


def test_validate_write_combines_checks(monkeypatch):
    """綜合檢查：同時驗證白名單與邊界。"""
    monkeypatch.setenv("OPC_WRITE_WHITELIST", "Temperature,Pressure,ValvePosition")
    from opc_service.config import OPCSettings

    settings = OPCSettings()
    monkeypatch.setattr(
        "opc_service.guard.settings", settings
    )
    from opc_service.guard import WriteGuard

    guard = WriteGuard()

    # 標籤不在白名單 → 拒絕
    ok, msg = guard.validate_write("FlowRate", 50.0)
    assert ok is False

    # 在白名單但超出邊界 → 拒絕
    ok, msg = guard.validate_write("Temperature", 200.0)
    assert ok is False

    # 通過所有檢查 → 允許
    ok, msg = guard.validate_write("Temperature", 80.0)
    assert ok is True


# ---- 審計日誌測試 ----

def test_audit_log_writes_jsonl(tmp_path, monkeypatch):
    """審計日誌：寫入 JSONL 檔案，每行一個 JSON 物件。"""
    monkeypatch.setenv("OPC_AUDIT_LOG_DIR", str(tmp_path))
    from opc_service.config import OPCSettings

    settings = OPCSettings()
    monkeypatch.setattr(
        "opc_service.audit.settings", settings
    )

    from opc_service.audit import AuditLogger

    logger = AuditLogger()
    logger.log_write("Temperature", 80.0, reason="測試寫入", result="success")

    # 確認檔案存在
    files = list(tmp_path.glob("opc_audit_*.jsonl"))
    assert len(files) == 1

    line = files[0].read_text(encoding="utf-8").strip()
    record = json.loads(line)
    assert record["tag_name"] == "Temperature"
    assert record["value"] == 80.0
    assert record["operation"] == "write"
    assert record["result"] == "success"


# ---- API 端點測試 ----

@pytest.fixture
def test_app():
    """建立測試用 FastAPI app（不連線真實 OPC）。"""
    from opc_service.app import app

    return app


def test_health_endpoint(test_app):
    """健康檢查端點回傳正確結構。"""
    client = TestClient(test_app)
    resp = client.get("/opc/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "opc_connected" in data


def _opc_auth(monkeypatch) -> dict[str, str]:
    monkeypatch.setenv("OPC_INTERNAL_TOKEN", "opc-test-token")
    return {"X-OPC-Internal": "opc-test-token"}


def test_read_endpoint_returns_error_when_disconnected(test_app, monkeypatch):
    """未連線 OPC 時，讀取端點回傳錯誤（不崩潰）。"""
    client = TestClient(test_app)
    resp = client.post(
        "/opc/read",
        json={"tag_names": ["Temperature"]},
        headers=_opc_auth(monkeypatch),
    )
    assert resp.status_code == 200
    data = resp.json()
    # 降級模式：回傳 tags 列表但含 error
    assert "tags" in data
    assert data.get("error") is not None or len(data["tags"]) == 0


def test_write_requires_internal_token(test_app, monkeypatch):
    monkeypatch.setenv("OPC_INTERNAL_TOKEN", "opc-test-token")
    client = TestClient(test_app)
    resp = client.post(
        "/opc/write",
        json={"entries": [{"tag_name": "Temperature", "value": 1.0}], "reason": "測試"},
    )
    assert resp.status_code == 401


def test_write_endpoint_with_guard(test_app, monkeypatch):
    """寫入端點：安全護欄拒絕不合規的寫入。"""
    headers = _opc_auth(monkeypatch)
    monkeypatch.setenv("OPC_WRITE_WHITELIST", "Temperature")
    from opc_service.config import OPCSettings

    settings = OPCSettings()
    monkeypatch.setattr(
        "opc_service.guard.settings", settings
    )

    client = TestClient(test_app)
    resp = client.post(
        "/opc/write",
        headers=headers,
        json={
            "entries": [
                {"tag_name": "FlowRate", "value": 50.0}
            ],
            "reason": "測試",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) == 1
    assert data["results"][0]["success"] is False


# ---- 6 級閉環情境測試 ----


def test_opc_graph_6_level_anomaly():
    """6 級閉環完整流程：異常檢測 → 決策 → 執行。"""
    from opc_service.graph import build_opc_graph

    # 诊断 LLM 响应（使用 suggested_actions）
    diagnose_response = json.dumps(
        {
            "anomaly_detected": True,
            "severity": "critical",
            "analysis": "溫度異常升高至 120°C，超出安全閾值 90°C",
            "root_cause": "冷卻水流量不足導致散熱失效",
            "suggested_actions": [
                {
                    "tag_name": "ValvePosition",
                    "value": 80.0,
                    "reason": "增加冷卻水流量",
                }
            ],
        },
        ensure_ascii=False,
    )

    # 决策 LLM 响应（优先级排序 + 风险评估）
    decide_response = json.dumps(
        {
            "summary": "立即增加冷卻水流量以降低溫度",
            "decisions": [
                {
                    "tag_name": "ValvePosition",
                    "value": 80.0,
                    "reason": "增加冷卻水流量以降低溫度",
                    "priority": "critical",
                    "risk": "low",
                    "risk_note": "閥門開度在安全範圍內",
                    "order": 1,
                }
            ],
        },
        ensure_ascii=False,
    )

    async def fake_read_tags(tag_names):
        return {
            "Temperature": {"value": 120.0, "quality": "Good"},
            "Pressure": {"value": 150.0, "quality": "Good"},
            "FlowRate": {"value": 5.0, "quality": "Good"},
            "ValvePosition": {"value": 20.0, "quality": "Good"},
        }

    async def fake_write_tags(entries, reason=""):
        return [
            {
                "tag_name": e["tag_name"],
                "success": True,
                "message": "寫入成功",
                "written_value": e["value"],
            }
            for e in entries
        ]

    fake_diagnose = MagicMock()
    fake_diagnose.side_effect = [diagnose_response]
    fake_decide = MagicMock()
    fake_decide.side_effect = [decide_response]

    with (
        patch(
            "opc_service.sense._read_opc_tags",
            side_effect=fake_read_tags,
        ),
        patch(
            "opc_service.act._write_opc_tags",
            side_effect=fake_write_tags,
        ),
        patch(
            "opc_service.diagnose.call_llm",
            side_effect=fake_diagnose,
        ),
        patch(
            "opc_service.decide.call_llm",
            side_effect=fake_decide,
        ),
    ):
        result = asyncio.run(
            build_opc_graph().ainvoke(
                {"query": "檢查製程狀態", "session_id": "test-session"}
            )
        )

    # 验证各阶段状态
    assert result["opc_anomaly_detected"] is True
    assert result["opc_diagnosis"]["severity"] == "critical"
    assert len(result["opc_decisions"]) == 1
    assert result["opc_decisions"][0]["priority"] == "critical"
    assert len(result["opc_actions"]) == 1
    assert result["opc_actions"][0]["success"] is True


def test_opc_graph_6_level_no_anomaly():
    """6 級閉環正常流程：無異常，無控制動作。"""
    from opc_service.graph import build_opc_graph

    diagnose_response = json.dumps(
        {
            "anomaly_detected": False,
            "severity": "normal",
            "analysis": "所有參數在安全範圍內",
            "root_cause": "",
            "suggested_actions": [],
        },
        ensure_ascii=False,
    )

    async def fake_read_tags(tag_names):
        return {
            "Temperature": {"value": 25.0, "quality": "Good"},
            "Pressure": {"value": 101.3, "quality": "Good"},
        }

    fake = MagicMock()
    fake.side_effect = [diagnose_response]

    with (
        patch(
            "opc_service.sense._read_opc_tags",
            side_effect=fake_read_tags,
        ),
        patch(
            "opc_service.diagnose.call_llm",
            side_effect=fake,
        ),
    ):
        result = asyncio.run(
            build_opc_graph().ainvoke(
                {"query": "檢查製程狀態", "session_id": "test-session"}
            )
        )

    assert result["opc_anomaly_detected"] is False
    assert result["opc_diagnosis"]["severity"] == "normal"
    assert result["opc_decisions"] == []
    assert result["opc_actions"] == []


# ---- 預處理節點測試 ----

def test_preprocess_filters_bad_quality():
    """預處理：過濾品質不良的讀數。"""
    from opc_service.preprocess import preprocess_opc

    state = {
        "opc_readings": {
            "Temperature": {"value": 25.0, "quality": "Good"},
            "Pressure": {"value": 101.3, "quality": "Bad"},
            "FlowRate": {"value": 50.0, "quality": "Uncertain"},
            "ValvePosition": {"value": 30.0, "quality": "Good"},
        }
    }

    result = asyncio.run(preprocess_opc(state))

    assert "Temperature" in result["opc_readings_clean"]
    assert "ValvePosition" in result["opc_readings_clean"]
    assert "Pressure" not in result["opc_readings_clean"]
    assert "FlowRate" not in result["opc_readings_clean"]
    assert result["opc_quality_report"]["good"] == 2
    assert result["opc_quality_report"]["bad"] == 2


def test_preprocess_empty_readings():
    """預處理：無讀數時返回空結果。"""
    from opc_service.preprocess import preprocess_opc

    result = asyncio.run(preprocess_opc({}))

    assert result["opc_readings_clean"] == {}
    assert result["opc_quality_report"]["total"] == 0


# ---- 分析節點測試 ----

def test_analyze_detects_threshold_violations():
    """分析：檢測超出閾值的讀數。"""
    from opc_service.analyze import analyze_opc

    state = {
        "opc_readings_clean": {
            "Temperature": {"value": 120.0, "quality": "Good"},
            "Pressure": {"value": 150.0, "quality": "Good"},
            "FlowRate": {"value": 50.0, "quality": "Good"},
        }
    }

    result = asyncio.run(analyze_opc(state))

    analysis = result["opc_analysis"]
    assert len(analysis["violations"]) == 1
    assert analysis["violations"][0]["tag"] == "Temperature"
    assert analysis["violations"][0]["direction"] == "high"
    assert analysis["violations"][0]["severity"] == "critical"
    assert "Temperature" in analysis["anomaly_tags"]


def test_analyze_normal_readings():
    """分析：正常讀數無違規。"""
    from opc_service.analyze import analyze_opc

    state = {
        "opc_readings_clean": {
            "Temperature": {"value": 25.0, "quality": "Good"},
            "Pressure": {"value": 101.3, "quality": "Good"},
        }
    }

    result = asyncio.run(analyze_opc(state))

    analysis = result["opc_analysis"]
    assert len(analysis["violations"]) == 0
    assert analysis["summary"] == "所有读数在安全范围内"


# ---- 決策節點測試 ----

def test_decide_skips_when_no_anomaly():
    """決策：無異常時跳過，返回空決策。"""
    from opc_service.decide import decide_opc

    state = {
        "opc_diagnosis": {"anomaly_detected": False},
    }

    result = asyncio.run(decide_opc(state))

    assert result["opc_decisions"] == []
    assert "无异常" in result["opc_decision_summary"]


def test_decide_with_anomaly():
    """決策：有異常時調用 LLM 制定策略。"""
    from opc_service.decide import decide_opc

    decide_response = json.dumps(
        {
            "summary": "優先處理溫度異常",
            "decisions": [
                {
                    "tag_name": "ValvePosition",
                    "value": 80.0,
                    "reason": "增加冷卻水流量",
                    "priority": "critical",
                    "risk": "low",
                    "risk_note": "在安全範圍內",
                    "order": 1,
                }
            ],
        },
        ensure_ascii=False,
    )

    state = {
        "opc_diagnosis": {
            "anomaly_detected": True,
            "severity": "critical",
            "root_cause": "冷卻不足",
            "analysis": "溫度過高",
            "suggested_actions": [
                {"tag_name": "ValvePosition", "value": 80.0, "reason": "降溫"}
            ],
        },
        "opc_analysis": {
            "violations": [
                {"tag": "Temperature", "value": 120.0, "threshold": 90.0,
                 "direction": "high", "severity": "critical"}
            ]
        },
        "opc_quality_report": {"total": 4, "good": 4, "bad": 0},
    }

    fake = MagicMock()
    fake.side_effect = [decide_response]

    with patch("opc_service.decide.call_llm", side_effect=fake):
        result = asyncio.run(decide_opc(state))

    assert len(result["opc_decisions"]) == 1
    assert result["opc_decisions"][0]["priority"] == "critical"
    assert result["opc_decisions"][0]["risk"] == "low"