"""控制面版聚合服務單元測試。

驗證：
1. 空資料（缺目錄/缺檔案/無任務）時降級回傳空結構不拋錯
2. 有資料時 stats/tasks/archives/opc_audit/capabilities 聚合正確
3. 損毀 JSONL 行被跳過，不中斷聚合
"""

import json

from backend.services import dashboard
from backend.services.task_manager import TaskRecord, task_manager


def _iso(ts: str) -> str:
    return ts


def _write_jsonl(path, records):
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
        encoding="utf-8",
    )


def _isolated_env(tmp_path, monkeypatch):
    """將存檔/審計/記憶目錄全部指向 tmp_path 隔離。"""
    archive_dir = tmp_path / "archives"
    audit_dir = tmp_path / "audit"
    archive_dir.mkdir()
    audit_dir.mkdir()
    monkeypatch.setenv("EVOL_ARCHIVE_DIR", str(archive_dir))
    monkeypatch.setenv("OPC_AUDIT_LOG_DIR", str(audit_dir))
    monkeypatch.setenv("EVOL_MEMORY_STORE_PATH", str(tmp_path / "memory.json"))
    monkeypatch.setattr(task_manager, "tasks", {})
    return archive_dir, audit_dir


def test_empty_data_degrades_safely(tmp_path, monkeypatch):
    _isolated_env(tmp_path, monkeypatch)

    data = dashboard.collect_dashboard()

    assert data["stats"]["tasks_total"] == 0
    assert data["stats"]["success_rate"] == 0
    assert data["stats"]["avg_score"] is None
    assert data["stats"]["memories_count"] == 0
    assert data["tasks"] == []
    assert data["archives"] == []
    assert data["opc_audit"]["recent"] == []
    assert data["opc_audit"]["summary"]["total"] == 0
    # 能力註冊表為靜態結構，始終完整
    keys = [c["key"] for c in data["capabilities"]]
    assert keys == [
        "llm", "reflection_loop", "company_runtime", "memory", "opc_ua", "archiver",
    ]


def test_aggregation_with_data(tmp_path, monkeypatch):
    archive_dir, audit_dir = _isolated_env(tmp_path, monkeypatch)

    # 任務記錄（含公司模式與花費）
    t1 = TaskRecord("task-a", "查詢一", "standard", "quick_task")
    t1.status = "completed"
    t1.score = 8.0
    t1.iteration = 1
    t1.answer = "回答一"
    t1.created_at = 1000.0
    t2 = TaskRecord("task-b", "查詢二", "company", "page_dev")
    t2.status = "failed"
    t2.resolved_path = "company"  # 統一模式：實際執行路徑
    t2.budget = {"task_spent": 0.5}
    t2.created_at = 2000.0
    monkeypatch.setattr(task_manager, "tasks", {"task-a": t1, "task-b": t2})

    # 對話存檔（含引用記憶；timestamp 降序驗證）
    _write_jsonl(archive_dir / "evo_2026-08-07.jsonl", [
        {
            "timestamp": _iso("2026-08-07T01:00:00Z"),
            "session_id": "s1",
            "user_query": "舊問題",
            "final_answer": "舊答案",
            "evaluation_score": 7.0,
            "memory_items": [],
        },
        {
            "timestamp": _iso("2026-08-07T02:00:00Z"),
            "session_id": "s2",
            "user_query": "新問題",
            "final_answer": "新答案",
            "evaluation_score": 9.0,
            "memory_items": ["記憶一", "記憶二"],
        },
        "not-a-json-line",  # 損毀行應被跳過
    ])

    # OPC 審計（success + blocked）
    _write_jsonl(audit_dir / "opc_audit_2026-08-07.jsonl", [
        {"timestamp": "2026-08-07T01:00:00Z", "operation": "write",
         "tag_name": "Temperature", "value": 80.0, "result": "success"},
        {"timestamp": "2026-08-07T02:00:00Z", "operation": "write",
         "tag_name": "FlowRate", "value": 50.0, "result": "blocked"},
    ])

    # 記憶庫
    (tmp_path / "memory.json").write_text(
        json.dumps([{"text": "m1"}, {"text": "m2"}, {"text": "m3"}]),
        encoding="utf-8",
    )

    data = dashboard.collect_dashboard()
    stats = data["stats"]

    # stats
    assert stats["tasks_total"] == 2
    assert stats["tasks_completed"] == 1
    assert stats["tasks_failed"] == 1
    assert stats["success_rate"] == 50.0
    assert stats["avg_score"] == 8.0
    assert stats["total_spent"] == 0.5
    assert stats["archives_count"] == 2
    assert stats["memories_count"] == 3
    assert stats["opc_total"] == 2
    assert stats["opc_blocked"] == 1

    # tasks 依 created_at 降序
    assert [t["task_id"] for t in data["tasks"]] == ["task-b", "task-a"]
    assert data["tasks"][1]["answer_preview"] == "回答一"
    # 最近任務附帶完整 answer / events / duration_sec（控制台訊息串用）
    assert data["tasks"][0]["answer"] == ""
    assert data["tasks"][1]["answer"] == "回答一"
    assert isinstance(data["tasks"][0]["events"], list)
    assert data["tasks"][0]["duration_sec"] >= 0

    # archives 依 timestamp 降序且跳過損毀行
    assert [a["session_id"] for a in data["archives"]] == ["s2", "s1"]

    # opc 審計匯總
    summary = data["opc_audit"]["summary"]
    assert summary["writes"] == 2
    assert summary["blocked"] == 1
    assert summary["success"] == 1

    # capabilities 動態統計
    caps = {c["key"]: c for c in data["capabilities"]}
    assert caps["reflection_loop"]["stats"]["usage"] == 2
    assert caps["company_runtime"]["stats"]["usage"] == 1
    assert "manager" in caps["company_runtime"]["stats"]["roles"]
    assert caps["memory"]["stats"]["count"] == 3
    # 引用次數僅計最近存檔窗口內的 memory_items（s2 有 2 筆）
    assert caps["memory"]["stats"]["referenced"] == 2
    assert caps["opc_ua"]["stats"]["blocked"] == 1
    assert caps["archiver"]["stats"]["files"] == 1


def test_missing_dirs_do_not_raise(tmp_path, monkeypatch):
    """目錄完全不存在時仍回傳空結構。"""
    monkeypatch.setenv("EVOL_ARCHIVE_DIR", str(tmp_path / "nope" / "archives"))
    monkeypatch.setenv("OPC_AUDIT_LOG_DIR", str(tmp_path / "nope" / "audit"))
    monkeypatch.setenv("EVOL_MEMORY_STORE_PATH", str(tmp_path / "nope.json"))
    monkeypatch.setattr(task_manager, "tasks", {})

    data = dashboard.collect_dashboard()

    assert data["stats"]["tasks_total"] == 0
    assert data["archives"] == []
    assert data["opc_audit"]["summary"]["total"] == 0
