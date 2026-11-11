"""軌跡統計（自 backend.services.trace_logger 抽出）。

LLM 調用分布與反思閉環指標彙總。
"""

from __future__ import annotations

import json
from typing import Any

from .paths import trace_dir


def aggregate_llm_call_stats(*, max_files: int = 80, max_events: int = 5000) -> dict[str, Any]:
    """從軌跡檔彙總 LLM 調用分布（模型 / 環節 / 耗時）。

    供監控中心「模型調用分布」分頁使用；掃描失敗時降級為空統計。
    """
    directory = trace_dir()
    if not directory.exists():
        return _empty_llm_call_stats()

    paths = sorted(
        directory.glob("trace_*.jsonl"),
        key=lambda p: p.stat().st_mtime if p.exists() else 0,
        reverse=True,
    )[:max_files]

    by_model: dict[str, dict[str, Any]] = {}
    by_phase: dict[str, int] = {}
    total_calls = 0
    total_cost = 0.0
    total_duration_ms = 0.0
    duration_samples = 0

    for path in paths:
        if total_calls >= max_events:
            break
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    if total_calls >= max_events:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if event.get("event") != "llm_call":
                        continue

                    model = str(event.get("model") or "unknown")
                    phase = str(event.get("phase") or "—")
                    cost = event.get("cost")
                    duration = event.get("duration_ms")

                    bucket = by_model.setdefault(
                        model,
                        {"count": 0, "cost": 0.0, "duration_ms": 0.0, "duration_samples": 0},
                    )
                    bucket["count"] += 1
                    if isinstance(cost, (int, float)):
                        bucket["cost"] += float(cost)
                        total_cost += float(cost)
                    if isinstance(duration, (int, float)):
                        bucket["duration_ms"] += float(duration)
                        bucket["duration_samples"] += 1
                        total_duration_ms += float(duration)
                        duration_samples += 1

                    by_phase[phase] = by_phase.get(phase, 0) + 1
                    total_calls += 1
        except OSError:
            continue

    models = []
    for model, stats in sorted(by_model.items(), key=lambda x: x[1]["count"], reverse=True):
        samples = int(stats.get("duration_samples") or 0)
        avg_ms = round(stats["duration_ms"] / samples, 1) if samples else None
        models.append({
            "model": model,
            "count": stats["count"],
            "share_pct": round(stats["count"] / total_calls * 100, 1) if total_calls else 0.0,
            "cost": round(stats["cost"], 6),
            "avg_duration_ms": avg_ms,
        })

    phases = [
        {"phase": phase, "count": count, "share_pct": round(count / total_calls * 100, 1) if total_calls else 0.0}
        for phase, count in sorted(by_phase.items(), key=lambda x: x[1], reverse=True)
    ]

    return {
        "total_calls": total_calls,
        "total_cost": round(total_cost, 6),
        "avg_duration_ms": round(total_duration_ms / duration_samples, 1) if duration_samples else None,
        "files_scanned": len(paths),
        "by_model": models,
        "by_phase": phases,
    }


def _empty_llm_call_stats() -> dict[str, Any]:
    return {
        "total_calls": 0,
        "total_cost": 0.0,
        "avg_duration_ms": None,
        "files_scanned": 0,
        "by_model": [],
        "by_phase": [],
    }


def _summarize_task_reflection(events: list[dict[str, Any]], task_id: str) -> dict[str, Any] | None:
    """從單任務軌跡事件彙總反思閉環指標。"""
    evaluations: list[tuple[int, float]] = []
    eval_ms = 0.0
    reflect_ms = 0.0
    improve_ms = 0.0
    max_iteration = 0
    early_stop = False
    last_ts = ""

    for event in events:
        last_ts = str(event.get("ts") or last_ts)
        et = event.get("event")
        iteration = int(event.get("iteration") or 0)

        if et == "evaluation":
            score = event.get("score")
            if isinstance(score, (int, float)):
                evaluations.append((iteration, float(score)))
            max_iteration = max(max_iteration, iteration)

        elif et == "llm_call":
            phase = str(event.get("phase") or "")
            duration = event.get("duration_ms")
            if not isinstance(duration, (int, float)):
                continue
            dur = float(duration)
            if phase in {"evaluate", "evaluation", "cross_eval"}:
                eval_ms += dur
            elif phase == "reflect":
                reflect_ms += dur
            elif phase == "improve":
                improve_ms += dur

        elif et in {"reflection", "improvement"}:
            max_iteration = max(max_iteration, iteration)

        elif et == "phase_change":
            phase = str(event.get("phase") or "")
            if "early_stop" in phase:
                early_stop = True

    if not evaluations and max_iteration == 0 and reflect_ms == 0:
        return None

    evaluations.sort(key=lambda x: x[0])
    scores = [s for _, s in evaluations]
    score_start = scores[0] if scores else None
    score_end = scores[-1] if scores else None
    score_delta = round(score_end - score_start, 2) if score_start is not None and score_end is not None else None
    iterations = max(max_iteration + 1, len({i for i, _ in evaluations}), 1 if evaluations else 0)

    return {
        "task_id": task_id,
        "iterations": iterations,
        "score_start": score_start,
        "score_end": score_end,
        "score_delta": score_delta,
        "evaluate_duration_ms": round(eval_ms, 1),
        "reflection_duration_ms": round(reflect_ms + improve_ms, 1),
        "loop_duration_ms": round(eval_ms + reflect_ms + improve_ms, 1),
        "early_stop": early_stop,
        "last_ts": last_ts,
    }


def aggregate_reflection_stats(*, max_files: int = 80, max_events: int = 8000) -> dict[str, Any]:
    """從軌跡檔彙總反思閉環鏈路指標（輪次、耗時、改進幅度）。

    供監控中心「系統指標」分頁使用；掃描失敗時降級為空統計。
    """
    directory = trace_dir()
    if not directory.exists():
        return _empty_reflection_stats()

    paths = sorted(
        directory.glob("trace_*.jsonl"),
        key=lambda p: p.stat().st_mtime if p.exists() else 0,
        reverse=True,
    )[:max_files]

    task_summaries: list[dict[str, Any]] = []
    early_stop_count = 0

    for path in paths:
        task_id = path.stem.replace("trace_", "")
        events: list[dict[str, Any]] = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    if len(events) >= max_events:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            continue

        summary = _summarize_task_reflection(events, task_id)
        if summary is None:
            continue
        if summary.get("early_stop"):
            early_stop_count += 1
        task_summaries.append(summary)

    if not task_summaries:
        return _empty_reflection_stats(files_scanned=len(paths))

    def _avg(key: str) -> float | None:
        values = [float(s[key]) for s in task_summaries if isinstance(s.get(key), (int, float))]
        return round(sum(values) / len(values), 2) if values else None

    deltas = [s["score_delta"] for s in task_summaries if isinstance(s.get("score_delta"), (int, float))]
    improved = sum(1 for d in deltas if d > 0)
    recent = sorted(task_summaries, key=lambda x: x.get("last_ts", ""), reverse=True)[:8]

    return {
        "tasks_analyzed": len(task_summaries),
        "files_scanned": len(paths),
        "early_stop_count": early_stop_count,
        "avg_iterations": _avg("iterations"),
        "avg_score_delta": round(sum(deltas) / len(deltas), 2) if deltas else None,
        "improvement_rate_pct": round(improved / len(deltas) * 100, 1) if deltas else 0.0,
        "avg_evaluate_duration_ms": _avg("evaluate_duration_ms"),
        "avg_reflection_duration_ms": _avg("reflection_duration_ms"),
        "avg_loop_duration_ms": _avg("loop_duration_ms"),
        "recent_cycles": recent,
    }


def _empty_reflection_stats(*, files_scanned: int = 0) -> dict[str, Any]:
    return {
        "tasks_analyzed": 0,
        "files_scanned": files_scanned,
        "early_stop_count": 0,
        "avg_iterations": None,
        "avg_score_delta": None,
        "improvement_rate_pct": 0.0,
        "avg_evaluate_duration_ms": None,
        "avg_reflection_duration_ms": None,
        "avg_loop_duration_ms": None,
        "recent_cycles": [],
    }
