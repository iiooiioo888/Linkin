"""模型調用分布與用戶反饋分析測試。"""

import json

from backend.core.user_feedback import feedback_analysis, record_feedback
from backend.services.trace_logger import aggregate_llm_call_stats, aggregate_reflection_stats


def test_aggregate_llm_call_stats_from_traces(tmp_path, monkeypatch):
    trace_dir = tmp_path / "traces"
    trace_dir.mkdir()
    trace_file = trace_dir / "trace_task1.jsonl"
    events = [
        {"event": "llm_call", "model": "deepseek-v4-flash", "phase": "generate", "duration_ms": 1200, "cost": 0.001},
        {"event": "llm_call", "model": "deepseek-v4-flash", "phase": "evaluate", "duration_ms": 800},
        {"event": "llm_call", "model": "qwen-turbo", "phase": "reflect", "duration_ms": 600},
        {"event": "phase_change", "phase": "evaluate"},
    ]
    with open(trace_file, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(ev, ensure_ascii=False) + "\n" for ev in events)

    monkeypatch.setenv("EVOL_TRACE_DIR", str(trace_dir))
    stats = aggregate_llm_call_stats()

    assert stats["total_calls"] == 3
    assert stats["files_scanned"] == 1
    assert len(stats["by_model"]) == 2
    assert stats["by_model"][0]["model"] == "deepseek-v4-flash"
    assert stats["by_model"][0]["count"] == 2
    assert stats["avg_duration_ms"] == 866.7
    phases = {row["phase"]: row["count"] for row in stats["by_phase"]}
    assert phases["generate"] == 1
    assert phases["evaluate"] == 1


def test_aggregate_reflection_stats_from_traces(tmp_path, monkeypatch):
    trace_dir = tmp_path / "traces"
    trace_dir.mkdir()
    trace_file = trace_dir / "trace_task_ref.jsonl"
    events = [
        {"event": "evaluation", "iteration": 0, "score": 6.2, "ts": "2026-08-31T10:00:00Z"},
        {"event": "llm_call", "phase": "reflect", "duration_ms": 900, "iteration": 0},
        {"event": "llm_call", "phase": "improve", "duration_ms": 1100, "iteration": 0},
        {"event": "improvement", "iteration": 0},
        {"event": "evaluation", "iteration": 1, "score": 8.1, "ts": "2026-08-31T10:01:00Z"},
        {"event": "llm_call", "phase": "evaluate", "duration_ms": 500, "iteration": 1},
        {"event": "phase_change", "phase": "early_stop"},
    ]
    with open(trace_file, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(ev, ensure_ascii=False) + "\n" for ev in events)

    monkeypatch.setenv("EVOL_TRACE_DIR", str(trace_dir))
    stats = aggregate_reflection_stats()

    assert stats["tasks_analyzed"] == 1
    assert stats["early_stop_count"] == 1
    assert stats["avg_iterations"] == 2.0
    assert stats["avg_score_delta"] == 1.9
    assert stats["avg_reflection_duration_ms"] == 2000.0
    assert len(stats["recent_cycles"]) == 1
    cycle = stats["recent_cycles"][0]
    assert cycle["task_id"] == "task_ref"
    assert cycle["score_start"] == 6.2
    assert cycle["score_end"] == 8.1


def test_feedback_analysis_word_cloud(tmp_path, monkeypatch):
    fb_path = tmp_path / "user_feedback.json"
    monkeypatch.setenv("EVOL_USER_FEEDBACK_PATH", str(fb_path))

    record_feedback(session_id="s1", signal="thumbs_up", score=9.0, comment="回答很清晰准确")
    record_feedback(session_id="s2", signal="thumbs_down", score=4.0, comment="不够完整，需要更多细节")
    record_feedback(session_id="s3", signal="copy", comment="清晰")

    analysis = feedback_analysis(top_words=10)
    assert analysis["total"] == 3
    assert analysis["signal_counts"]["thumbs_up"] == 1
    assert analysis["signal_counts"]["copy"] == 1
    assert analysis["score_buckets"]["high"] == 1
    assert analysis["score_buckets"]["low"] == 1
    assert len(analysis["word_cloud"]) >= 1
    words = {w["word"] for w in analysis["word_cloud"]}
    assert "清晰" in words or "准确" in words or "完整" in words


def test_optimization_monitor_includes_model_calls_and_feedback():
    from backend.services.optimization_monitor import collect_optimization_monitor

    data = collect_optimization_monitor()
    assert "model_calls" in data
    assert "by_model" in data["model_calls"]
    assert "reflection_trace" in data
    assert "recent_cycles" in data["reflection_trace"]
    assert "feedback_analysis" in data
    assert "word_cloud" in data["feedback_analysis"]
