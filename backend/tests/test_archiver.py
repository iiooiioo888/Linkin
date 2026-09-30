"""Task 8.6：文本化存檔單元測試。

驗證：
1. 存檔記錄欄位映射正確（直接通過 / 經歷反思兩種情境）
2. JSONL 以日期分割檔案寫入且可附加
3. 完整圖執行後存檔節點正常產出檔案
"""

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from backend.core.graph import build_graph
from backend.services.archiver import (
    build_archive_record,
    save_session_archive,
    save_session_archive_sync,
)


def test_record_mapping_without_reflection():
    state = {
        "query": "如何重設密碼？",
        "initial_answer": "請至設定頁重設。",
        "current_answer": "請至設定頁重設。",
        "final_answer": "請至設定頁重設。",
        "score": 9.0,
        "evaluation": {"score": 9, "strengths": "準確", "weaknesses": ""},
    }
    record = build_archive_record(state, "session-1")

    assert record["session_id"] == "session-1"
    assert record["user_query"] == "如何重設密碼？"
    assert record["initial_answer"] == "請至設定頁重設。"
    assert record["evaluation_score"] == 9.0
    assert record["evaluation_feedback"] == "準確"
    assert record["needs_improvement"] is False
    assert record["reflection"] is None
    assert record["improved_answer"] is None
    assert record["final_answer"] == "請至設定頁重設。"
    assert "model" in record["metadata"]


def test_record_mapping_with_reflection():
    state = {
        "query": "問題",
        "initial_answer": "差答案",
        "current_answer": "好答案",
        "final_answer": "好答案",
        "score": 8.5,
        "evaluation": {"score": 8.5, "strengths": "", "weaknesses": "缺步驟"},
        "reflections": [
            {"iteration": 1, "score": 4.0, "critique": "根因", "suggestion": "建議"}
        ],
        "iteration": 1,
        "memory_saved": True,
    }
    record = build_archive_record(state, "session-2")

    assert record["needs_improvement"] is True
    assert record["reflection"] == state["reflections"]
    assert record["improved_answer"] == "好答案"
    assert record["evaluation_feedback"] == "缺步驟"
    assert record["metadata"]["iterations"] == 1
    assert record["metadata"]["memory_saved"] is True

def test_save_archive_writes_date_partitioned_jsonl(tmp_path, monkeypatch):
    monkeypatch.setenv("EVOL_ARCHIVE_DIR", str(tmp_path))
    state = {"query": "Q", "final_answer": "A", "score": 9.0}

    path = asyncio.run(save_session_archive(state, "session-3"))

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert path.name == f"evo_{date_str}.jsonl"
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["session_id"] == "session-3"

    # 再次寫入應追加而非覆寫（同步版本亦同）
    asyncio.run(save_session_archive(state, "session-4"))
    save_session_archive_sync(state, "session-5")
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3


def test_full_graph_archives_session(tmp_path, monkeypatch):
    monkeypatch.setenv("EVOL_ARCHIVE_DIR", str(tmp_path))
    responses = [
        "初始回答",
        json.dumps({"score": 9, "strengths": "準確", "weaknesses": ""}),
    ]
    calls = []

    def fake_call_llm(prompt, system=None, model=None, **kwargs):
        calls.append(prompt)
        return responses[len(calls) - 1]

    with (
        patch("backend.core.nodes.call_llm", side_effect=fake_call_llm),
        patch("backend.core.evaluation.call_llm", side_effect=fake_call_llm),
        patch("backend.core.nodes._memory_store", MagicMock()),
    ):
        result = asyncio.run(build_graph().ainvoke(
            {"query": "測試問題", "session_id": "sess-graph-1"}
        ))

    assert result["archived"] is True
    files = list(tmp_path.glob("evo_*.jsonl"))
    assert len(files) == 1
    record = json.loads(files[0].read_text(encoding="utf-8").strip())
    assert record["session_id"] == "sess-graph-1"
    assert record["final_answer"] == "初始回答"
    assert record["needs_improvement"] is False