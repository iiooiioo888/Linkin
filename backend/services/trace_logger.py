"""思考過程記錄器（Trace Logger）。

完整記錄任務執行過程中的所有記憶、上下文、思考過程：
- LLM 調用（prompt、response、model、cost、耗時）
- 上下文注入（記憶檢索結果、依賴產物、角色記憶）
- 評估/反思的完整內容
- 工具調用與結果
- 階段切換與狀態快照

寫入 backend/data/traces/<task_id>.jsonl，每行一個事件。
支持斷點續跑：任務恢復時可讀取已有軌跡。
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 預設軌跡目錄：backend/data/traces
DEFAULT_TRACE_DIR = Path(__file__).resolve().parent.parent / "data" / "traces"

# 檢查點目錄：backend/data/checkpoints
DEFAULT_CHECKPOINT_DIR = Path(__file__).resolve().parent.parent / "data" / "checkpoints"


def trace_dir() -> Path:
    """解析軌跡目錄（每次呼叫時解析，方便測試以環境變數覆蓋）。"""
    return Path(os.getenv("EVOL_TRACE_DIR", str(DEFAULT_TRACE_DIR)))


def checkpoint_dir() -> Path:
    """解析檢查點目錄。"""
    return Path(os.getenv("EVOL_CHECKPOINT_DIR", str(DEFAULT_CHECKPOINT_DIR)))


def trace_path(task_id: str) -> Path:
    """指定任務的 JSONL 軌跡檔案路徑。"""
    return trace_dir() / f"trace_{task_id}.jsonl"


def checkpoint_path(task_id: str) -> Path:
    """指定任務的檢查點檔案路徑。"""
    return checkpoint_dir() / f"checkpoint_{task_id}.json"


def utc_now_iso() -> str:
    """當前 UTC 時間的 ISO 字串。"""
    return datetime.now(timezone.utc).isoformat()


def eval_trace_kwargs(multi_dim: Any) -> dict[str, str]:
    """多維評估 → log_evaluation 欄位（feedback/strengths/weaknesses/raw_response）。

    chat 流與後台任務管線共用，確保兩條路徑的軌跡評估明細一致。
    """
    if not isinstance(multi_dim, dict) or not multi_dim:
        return {}
    dims = ("accuracy", "completeness", "clarity", "relevance")
    labels = {"accuracy": "準確", "completeness": "完整", "clarity": "清晰", "relevance": "相關"}

    def _fmt(dim: str) -> str:
        d = multi_dim.get(dim) or {}
        if not isinstance(d, dict):
            return ""
        score = d.get("score")
        reason = str(d.get("reason") or "").strip()
        return f"{labels[dim]}{score}：{reason[:120]}" if reason else f"{labels[dim]}{score}"

    parts = [p for p in (_fmt(x) for x in dims) if p]
    return {
        "feedback": f"來源 {multi_dim.get('source', '?')} · " + " / ".join(parts),
        "strengths": " / ".join(parts[:2]),
        "weaknesses": " / ".join(parts[2:]),
        "raw_response": json.dumps(multi_dim, ensure_ascii=False)[:3000],
    }


class TraceLogger:
    """任務思考過程記錄器。

    每個任務一個實例，所有事件寫入對應的 JSONL 檔案。
    寫入失敗僅記錄警告，絕不中斷主流程。

    使用範例：
        >>> tracer = TraceLogger("task_abc123")
        >>> tracer.log_llm_call(prompt="...", response="...", model="gpt-4o")
        >>> tracer.log_context_injection(source="memory", items=[...])
        >>> tracer.log_evaluation(score=8.5, feedback="...")
    """

    def __init__(self, task_id: str):
        self.task_id = task_id
        self._seq = 0  # 事件序號

    def _write(self, event_type: str, data: dict[str, Any]) -> None:
        """寫入一筆事件到 JSONL 檔案。"""
        self._seq += 1
        record = {
            "seq": self._seq,
            "ts": utc_now_iso(),
            "task_id": self.task_id,
            "event": event_type,
            **data,
        }
        try:
            directory = trace_dir()
            directory.mkdir(parents=True, exist_ok=True)
            path = trace_path(self.task_id)
            line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
        except OSError as exc:
            logger.warning("軌跡寫入失敗（已忽略）：task_id=%s, %s", self.task_id, exc)

    # ── LLM 調用記錄 ──

    def log_llm_call(
        self,
        prompt: str,
        response: str,
        *,
        model: str | None = None,
        system: str | None = None,
        cost: float | None = None,
        duration_ms: float | None = None,
        phase: str = "",
        role: str = "",
        item_id: str = "",
        iteration: int = 0,
        truncated: bool = False,
        full: bool = False,
    ) -> None:
        """記錄一次完整的 LLM 調用（prompt + response）。

        full=True 時不截斷（角色 I/O 監察用；前端負責分塊渲染）。
        """
        cap = 10 ** 9 if full else 8000
        sys_cap = 10 ** 9 if full else 2000
        self._write("llm_call", {
            "phase": phase,
            "role": role,
            "item_id": item_id,
            "iteration": iteration,
            "model": model,
            "system": (system[:sys_cap] if system else None),
            "prompt": prompt[:cap] if not truncated else prompt[:cap] + "...[truncated]",
            "response": response[:cap] if not truncated else response[:cap] + "...[truncated]",
            "prompt_length": len(prompt),
            "response_length": len(response),
            "cost": cost,
            "duration_ms": duration_ms,
        })

    # ── 上下文注入記錄 ──

    def log_context_injection(
        self,
        source: str,
        items: list[dict[str, Any]] | list[str],
        *,
        phase: str = "",
        query: str = "",
        count: int | None = None,
    ) -> None:
        """記錄上下文注入（記憶檢索、依賴產物、角色記憶等）。

        Args:
            source: 來源類型（memory / dependency / role_memory / history）
            items: 注入的內容列表
            phase: 當前階段
            query: 檢索查詢
            count: 項目數量
        """
        self._write("context_injection", {
            "source": source,
            "phase": phase,
            "query": query[:500] if query else "",
            "count": count if count is not None else len(items),
            "items": [
                (item if isinstance(item, str) else json.dumps(item, ensure_ascii=False, default=str))[:1000]
                for item in items[:20]  # 最多記錄 20 條
            ],
        })

    # ── 評估記錄 ──

    def log_evaluation(
        self,
        score: float | None,
        feedback: str = "",
        *,
        iteration: int = 0,
        phase: str = "evaluate",
        raw_response: str = "",
        strengths: str = "",
        weaknesses: str = "",
    ) -> None:
        """記錄評估結果（分數、回饋、優缺點）。"""
        self._write("evaluation", {
            "phase": phase,
            "iteration": iteration,
            "score": score,
            "feedback": feedback[:2000],
            "strengths": strengths[:1000],
            "weaknesses": weaknesses[:1000],
            "raw_response": raw_response[:3000],
        })

    # ── 反思記錄 ──

    def log_reflection(
        self,
        reflection: str,
        *,
        iteration: int = 0,
        phase: str = "reflect",
        current_answer_preview: str = "",
    ) -> None:
        """記錄反思內容。"""
        self._write("reflection", {
            "phase": phase,
            "iteration": iteration,
            "reflection": reflection[:3000],
            "current_answer_preview": current_answer_preview[:500],
        })

    # ── 改進記錄 ──

    def log_improvement(
        self,
        improved_answer: str,
        *,
        iteration: int = 0,
        phase: str = "improve",
        based_on_reflection: str = "",
    ) -> None:
        """記錄改進後的回答。"""
        self._write("improvement", {
            "phase": phase,
            "iteration": iteration,
            "improved_answer": improved_answer[:5000],
            "based_on_reflection": based_on_reflection[:1000],
        })

    # ── 階段切換記錄 ──

    def log_phase_change(
        self,
        phase: str,
        *,
        data: dict[str, Any] | None = None,
    ) -> None:
        """記錄階段切換。"""
        self._write("phase_change", {
            "phase": phase,
            **(data or {}),
        })

    # ── 工具調用記錄 ──

    def log_tool_call(
        self,
        tool: str,
        args: dict[str, Any],
        result: str,
        *,
        success: bool = True,
        phase: str = "",
        item_id: str = "",
        duration_ms: float | None = None,
    ) -> None:
        """記錄工具調用與結果。"""
        self._write("tool_call", {
            "phase": phase,
            "item_id": item_id,
            "tool": tool,
            "args": args,
            "result": result[:3000],
            "success": success,
            "duration_ms": duration_ms,
        })

    # ── 狀態快照記錄 ──

    def log_state_snapshot(
        self,
        state: dict[str, Any],
        *,
        phase: str = "",
        label: str = "",
    ) -> None:
        """記錄完整狀態快照（供斷點續跑參考）。"""
        # 過濾不可序列化的內容
        safe_state = {}
        for k, v in state.items():
            try:
                json.dumps(v, ensure_ascii=False, default=str)
                safe_state[k] = v
            except (TypeError, ValueError):
                safe_state[k] = str(v)[:500]
        self._write("state_snapshot", {
            "phase": phase,
            "label": label,
            "state": safe_state,
        })

    # ── 記憶操作記錄 ──

    def log_memory_operation(
        self,
        operation: str,
        *,
        memory_id: str = "",
        text: str = "",
        metadata: dict[str, Any] | None = None,
        phase: str = "",
    ) -> None:
        """記錄記憶庫操作（保存/檢索/刪除）。"""
        self._write("memory_operation", {
            "phase": phase,
            "operation": operation,
            "memory_id": memory_id,
            "text": text[:2000],
            "metadata": metadata or {},
        })

    # ── 錯誤記錄 ──

    def log_error(
        self,
        error: str,
        *,
        phase: str = "",
        recoverable: bool = True,
        context: str = "",
    ) -> None:
        """記錄錯誤事件。"""
        self._write("error", {
            "phase": phase,
            "error": error[:2000],
            "recoverable": recoverable,
            "context": context[:1000],
        })

    # ── 自定義事件 ──

    def log_custom(self, event_type: str, data: dict[str, Any]) -> None:
        """記錄自定義事件。"""
        self._write(event_type, data)

    # ── 公司事件鏡像 ──

    def log_company_event(self, event_name: str, data: dict[str, Any]) -> None:
        """把一條 CompanyEvent 鏡像為軌跡事件（角色 I/O 監察資料源）。

        事件名原樣保留（work_item_done / tool_call / review_pass ...），
        並把 item_id/title/role 等欄位提升到頂層，前端按角色與
        工作項聚合時不必理解每種事件的負載結構。
        """
        role = data.get("role") or data.get("assignee") or ""
        if not role and event_name in {"review_pass", "review_rework", "review_force_done", "inspector_verdict"}:
            role = "reviewer"
        elif not role and event_name in {"campaign_planned", "grill_raised", "grill_resolved"}:
            role = "requirement_auditor"
        payload: dict[str, Any] = {
            "phase": data.get("phase", ""),
            "role": str(role or ""),
            "item_id": str(data.get("item_id", "") or ""),
            "title": str(data.get("title", "") or ""),
        }
        for key, value in data.items():
            if key in payload:
                continue
            try:
                json.dumps(value, ensure_ascii=False, default=str)
                payload[key] = value
            except (TypeError, ValueError):
                payload[key] = str(value)[:500]
        self._write(event_name, payload)


# ═══════════════════════════════════════════════════════════
# 檢查點管理
# ═══════════════════════════════════════════════════════════


def save_checkpoint(task_id: str, checkpoint_data: dict[str, Any]) -> Path | None:
    """保存任務檢查點到本地 JSON 檔案。

    Args:
        task_id: 任務 ID
        checkpoint_data: 檢查點數據（orchestrator.to_checkpoint() 的結果）

    Returns:
        寫入的檔案路徑；失敗時回傳 None
    """
    try:
        directory = checkpoint_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = checkpoint_path(task_id)
        data = {
            "task_id": task_id,
            "saved_at": utc_now_iso(),
            "version": 1,
            **checkpoint_data,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        logger.info("檢查點已保存：task_id=%s", task_id)
        return path
    except OSError as exc:
        logger.warning("檢查點保存失敗：task_id=%s, %s", task_id, exc)
        return None


def load_checkpoint(task_id: str) -> dict[str, Any] | None:
    """載入任務檢查點。

    Args:
        task_id: 任務 ID

    Returns:
        檢查點數據；不存在或讀取失敗時回傳 None
    """
    path = checkpoint_path(task_id)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("檢查點載入失敗：task_id=%s, %s", task_id, exc)
        return None


def delete_checkpoint(task_id: str) -> bool:
    """刪除任務檢查點（任務完成後清理）。"""
    path = checkpoint_path(task_id)
    if path.exists():
        try:
            path.unlink()
            return True
        except OSError:
            return False
    return False


def delete_trace(task_id: str) -> bool:
    """刪除任務軌跡 JSONL（取消／過期清理）。"""
    path = trace_path(task_id)
    if path.exists():
        try:
            path.unlink()
            return True
        except OSError:
            return False
    return False


def list_checkpoints() -> list[dict[str, Any]]:
    """列出所有可恢復的檢查點。

    Returns:
        檢查點摘要列表（task_id, saved_at, goal, phase）
    """
    directory = checkpoint_dir()
    if not directory.exists():
        return []
    results = []
    for path in directory.glob("checkpoint_*.json"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            results.append({
                "task_id": data.get("task_id", ""),
                "saved_at": data.get("saved_at", ""),
                "goal": data.get("goal", ""),
                "phase": data.get("phase", ""),
                "config_name": data.get("config_name", ""),
                "work_item_count": len(data.get("work_items", [])),
            })
        except (OSError, json.JSONDecodeError):
            continue
    results.sort(key=lambda x: x.get("saved_at", ""), reverse=True)
    return results


def read_trace(
    task_id: str,
    limit: int = 100,
    offset: int = 0,
    *,
    event: str | None = None,
    role: str | None = None,
    item_id: str | None = None,
) -> list[dict[str, Any]]:
    """讀取任務軌跡記錄。

    Args:
        task_id: 任務 ID
        limit: 返回條數上限
        offset: 跳過前 N 條（篩選後再分頁）
        event: 事件名篩選（逗號分隔多值，如 work_item_done,llm_call）
        role: 角色篩選（逗號分隔多值）
        item_id: 工作項篩選

    Returns:
        事件記錄列表（按時間順序）
    """
    path = trace_path(task_id)
    if not path.exists():
        return []
    events = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except OSError:
        return []
    if event:
        wanted = {e.strip() for e in event.split(",") if e.strip()}
        if wanted:
            events = [ev for ev in events if ev.get("event") in wanted]
    if role:
        wanted_roles = {r.strip() for r in role.split(",") if r.strip()}
        if wanted_roles:
            events = [ev for ev in events if ev.get("role") in wanted_roles]
    if item_id:
        events = [ev for ev in events if ev.get("item_id") == item_id]
    return events[offset:offset + limit]


def trace_event_counts(task_id: str) -> dict[str, int]:
    """統計任務軌跡中各事件型的條數（前端篩選器計數用）。"""
    path = trace_path(task_id)
    counts: dict[str, int] = {}
    if not path.exists():
        return counts
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line).get("event", "?")
                except json.JSONDecodeError:
                    continue
                counts[ev] = counts.get(ev, 0) + 1
    except OSError:
        return {}
    return counts


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


def list_traces(limit: int = 50) -> list[dict[str, Any]]:
    """列出所有軌跡檔案摘要。

    Returns:
        軌跡摘要列表（task_id, event_count, first_ts, last_ts, file_size）
    """
    directory = trace_dir()
    if not directory.exists():
        return []
    results = []
    for path in directory.glob("trace_*.jsonl"):
        try:
            task_id = path.stem.replace("trace_", "")
            stat = path.stat()
            # 讀取首行和末行獲取時間範圍
            first_ts = ""
            last_ts = ""
            event_count = 0
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        event_count += 1
                        try:
                            data = json.loads(line)
                            if not first_ts:
                                first_ts = data.get("ts", "")
                            last_ts = data.get("ts", "")
                        except json.JSONDecodeError:
                            continue
            results.append({
                "task_id": task_id,
                "event_count": event_count,
                "first_ts": first_ts,
                "last_ts": last_ts,
                "file_size_kb": round(stat.st_size / 1024, 1),
            })
        except OSError:
            continue
    results.sort(key=lambda x: str(x.get("last_ts", "")), reverse=True)
    return results[:limit]