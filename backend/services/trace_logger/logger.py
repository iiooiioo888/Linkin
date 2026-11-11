"""TraceLogger 類別（自 backend.services.trace_logger 抽出）。

任務思考過程 JSONL 記錄器（LLM 調用／上下文／評估／反思／工具／公司事件鏡像）。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .paths import trace_dir, trace_path, utc_now_iso

logger = logging.getLogger(__name__)


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
