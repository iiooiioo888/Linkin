"""Context 洞察聚合（對齊 dsh-context 資訊架構）。

從任務軌跡 JSONL 組裝可視化所需結構：
- **stats**：回合／LLM 呼叫／注入／工具／記憶操作計數與估算 token
- **composition**：當前上下文組成（六色類別）
- **trend**：每次 llm_call 為一步的組成趨勢
- **events**：注入／壓縮／剪枝／切換／模式等上下文演進事件
- **browser**：選定步驟的元素清單（可展開內容）

估算採固定密度啟發式（CHARS_PER_TOKEN），與 ContextAssembler 一致；
不做真實 tokenizer，避免測試依賴與供應商差異。
"""

from __future__ import annotations

from typing import Any

from backend.services.trace_logger import list_traces, read_trace, trace_event_counts

CHARS_PER_TOKEN = 2

# 六色組成類別（對齊 dsh-context Current Context）
COMPOSITION_KEYS = (
    "system",
    "tools",
    "user",
    "injected",
    "assistant",
    "tool_results",
)

EVENT_KIND_MAP = {
    "context_injection": "inject",
    "memory_operation": "inject",
    "phase_change": "switch",
    "tool_call": "mode",
    "state_snapshot": "mode",
    "llm_call": "mode",
    "context_compact": "compact",
    "context_prune": "prune",
}

# 工具名 → File Activity 用途（對齊 dsh-context Read/Written/Searched/Images）
_FILE_PURPOSE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("read", ("read_file", "read", "cat", "open", "get_file", "view")),
    ("written", ("write_file", "write", "edit", "str_replace", "apply_patch", "create_file", "save")),
    ("searched", ("search", "grep", "glob", "find", "rg", "codebase_search")),
    ("images", ("read_image", "image", "screenshot", "vision")),
)


def _est_tokens(text: str | None) -> int:
    if not text:
        return 0
    return max(0, len(text) // CHARS_PER_TOKEN)


def _item_text(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        for key in ("text", "content", "summary", "prompt", "response"):
            val = item.get(key)
            if isinstance(val, str) and val.strip():
                return val
        return str(item)[:1000]
    return str(item)[:1000]


def _empty_composition() -> dict[str, dict[str, Any]]:
    return {
        key: {"tokens": 0, "items": 0, "share": 0.0}
        for key in COMPOSITION_KEYS
    }


def _normalize_shares(comp: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    total = sum(int(v.get("tokens") or 0) for v in comp.values()) or 1
    for key in COMPOSITION_KEYS:
        tok = int(comp[key].get("tokens") or 0)
        comp[key]["share"] = round(tok / total, 4)
    return comp


def _classify_llm_call(ev: dict[str, Any]) -> dict[str, int]:
    """將單次 llm_call 粗分到組成類別（啟發式）。"""
    system = _est_tokens(ev.get("system"))
    prompt = _est_tokens(ev.get("prompt"))
    response = _est_tokens(ev.get("response"))
    # prompt 無法精確拆 user/injected；以比例近似：多數為 user，少量預留給注入痕跡
    injected_hint = 0
    prompt_l = str(ev.get("prompt") or "")
    if "[memos]" in prompt_l.lower() or "[openviking]" in prompt_l.lower() or "[weknora]" in prompt_l.lower():
        injected_hint = min(prompt // 3, prompt)
    user = max(0, prompt - injected_hint)
    return {
        "system": system,
        "tools": 0,
        "user": user,
        "injected": injected_hint,
        "assistant": response,
        "tool_results": 0,
    }


def _accumulate(comp: dict[str, dict[str, Any]], deltas: dict[str, int], *, items: dict[str, int] | None = None) -> None:
    for key in COMPOSITION_KEYS:
        comp[key]["tokens"] = int(comp[key]["tokens"]) + int(deltas.get(key) or 0)
        if items:
            comp[key]["items"] = int(comp[key]["items"]) + int(items.get(key) or 0)


def _tool_source_chip(tool_name: str) -> str:
    """對齊 dsh-context 來源晶片：tool-*／dsh-*／mcp:*／plugin:*。"""
    name = (tool_name or "tool").strip() or "tool"
    low = name.lower().replace("-", "_")
    if low.startswith("mcp_") or low.startswith("mcp:") or "mcp/" in low:
        server = name.split(":", 1)[-1] if ":" in name else name
        return f"mcp:{server}"
    if low.startswith("dsh") or "dsh_" in low:
        return f"dsh-{name}"
    if any(k in low for k in ("memos", "openviking", "weknora", "ouroboros", "openpencil", "yao")):
        return f"plugin:{name}"
    return f"tool:{name}"


def _guess_file_purpose(tool_name: str) -> str | None:
    low = (tool_name or "").lower().replace("-", "_")
    for purpose, needles in _FILE_PURPOSE_RULES:
        if any(n in low for n in needles):
            return purpose
    return None


def _extract_file_path(args_raw: Any, result_s: str = "") -> str:
    if isinstance(args_raw, dict):
        for key in ("path", "file", "file_path", "filepath", "target", "uri"):
            val = args_raw.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()[:240]
        q = args_raw.get("q") or args_raw.get("query") or args_raw.get("pattern")
        if isinstance(q, str) and q.strip():
            return f"query:{q.strip()[:120]}"
    if isinstance(args_raw, str) and args_raw.strip():
        return args_raw.strip()[:240]
    if result_s:
        return result_s.splitlines()[0][:240] if result_s else ""
    return ""


def _line_delta(args_raw: Any, result_s: str = "") -> tuple[int, int]:
    """粗估 +added / −removed（無真實 diff 時用字元啟發式）。"""
    added = removed = 0
    if isinstance(args_raw, dict):
        for key in ("new_string", "content", "text", "patch"):
            val = args_raw.get(key)
            if isinstance(val, str) and val:
                added += max(1, val.count("\n") + 1)
        for key in ("old_string", "previous"):
            val = args_raw.get(key)
            if isinstance(val, str) and val:
                removed += max(1, val.count("\n") + 1)
    if not added and result_s:
        added = max(0, result_s.count("\n") // 4)
    return added, removed


def build_context_insight(
    task_id: str,
    *,
    step: int | None = None,
    max_events: int = 2000,
) -> dict[str, Any]:
    """聚合指定任務的 Context 洞察。

    ``step`` 為 0-based llm_call 序號；None 表示最新一步（或無步驟時空組成）。
    """
    events = read_trace(task_id, limit=max_events, offset=0)
    counts = trace_event_counts(task_id)

    llm_steps: list[dict[str, Any]] = []
    insight_events: list[dict[str, Any]] = []
    running = _empty_composition()
    trend: list[dict[str, Any]] = []
    pending_marks: list[dict[str, str]] = []

    inject_items_total = 0
    tool_calls = 0
    memory_ops = 0
    total_cost = 0.0
    total_duration_ms = 0.0
    duration_n = 0
    tool_duration_ms = 0.0
    compact_count = 0
    prune_count = 0

    # File Activity：path → {path, purposes, ops, added, removed, hits, last_seq, last_ts}
    file_map: dict[str, dict[str, Any]] = {}
    # Agent Network：role → {role, llm_calls, tokens_in, tokens_out, cost, duration_ms}
    agent_map: dict[str, dict[str, Any]] = {}

    def _mark(kind: str, label: str) -> None:
        entry = {"kind": kind, "label": label}
        if trend:
            trend[-1]["marks"].append(entry)
        else:
            pending_marks.append(entry)

    def _touch_file(
        *,
        path: str,
        purpose: str,
        tool: str,
        seq: Any,
        ts: Any,
        added: int = 0,
        removed: int = 0,
        hits: int = 0,
    ) -> None:
        if not path:
            path = f"(unnamed:{tool})"
        row = file_map.get(path)
        if not row:
            row = {
                "path": path,
                "purposes": set(),
                "ops": [],
                "added": 0,
                "removed": 0,
                "hits": 0,
                "last_seq": seq,
                "last_ts": ts,
            }
            file_map[path] = row
        row["purposes"].add(purpose)
        row["added"] += int(added)
        row["removed"] += int(removed)
        row["hits"] += int(hits)
        row["last_seq"] = seq
        row["last_ts"] = ts
        row["ops"].append(
            {
                "purpose": purpose,
                "tool": tool,
                "seq": seq,
                "ts": ts,
                "added": added,
                "removed": removed,
            }
        )

    def _touch_agent(role: str, *, tin: int, tout: int, cost: float, dur: float) -> None:
        key = role or "unknown"
        row = agent_map.get(key)
        if not row:
            row = {
                "role": key,
                "llm_calls": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "cost": 0.0,
                "duration_ms": 0.0,
                "parent": None,
            }
            agent_map[key] = row
        row["llm_calls"] += 1
        row["tokens_in"] += tin
        row["tokens_out"] += tout
        row["cost"] = round(float(row["cost"]) + cost, 6)
        row["duration_ms"] = round(float(row["duration_ms"]) + dur, 1)

    for ev in events:
        et = str(ev.get("event") or "")
        seq = ev.get("seq")
        ts = ev.get("ts")

        if et == "llm_call":
            deltas = _classify_llm_call(ev)
            _accumulate(
                running,
                deltas,
                items={
                    "system": 1 if deltas["system"] else 0,
                    "user": 1 if deltas["user"] else 0,
                    "injected": 1 if deltas["injected"] else 0,
                    "assistant": 1 if deltas["assistant"] else 0,
                },
            )
            snapshot = _normalize_shares(
                {
                    k: {"tokens": int(running[k]["tokens"]), "items": int(running[k]["items"]), "share": 0.0}
                    for k in COMPOSITION_KEYS
                }
            )
            step_idx = len(llm_steps)
            tin = _est_tokens(ev.get("prompt")) + _est_tokens(ev.get("system"))
            tout = _est_tokens(ev.get("response"))
            cost_f = float(ev.get("cost") or 0) if isinstance(ev.get("cost"), (int, float)) else 0.0
            dur_f = float(ev.get("duration_ms") or 0) if isinstance(ev.get("duration_ms"), (int, float)) else 0.0
            llm_steps.append(
                {
                    "step": step_idx,
                    "seq": seq,
                    "ts": ts,
                    "model": ev.get("model"),
                    "phase": ev.get("phase") or "",
                    "role": ev.get("role") or "",
                    "cost": ev.get("cost"),
                    "duration_ms": ev.get("duration_ms"),
                    "prompt_tokens_est": tin,
                    "completion_tokens_est": tout,
                    "delta": deltas,
                    "composition": snapshot,
                    "system": (ev.get("system") or "")[:2000],
                    "prompt": (ev.get("prompt") or "")[:4000],
                    "response": (ev.get("response") or "")[:4000],
                }
            )
            marks = list(pending_marks)
            pending_marks.clear()
            total_now = sum(int(snapshot[k]["tokens"]) for k in COMPOSITION_KEYS)
            delta_tokens = sum(deltas.values())
            # 窗口相對上一步縮小 → 視為 compact（對齊 dsh-context ✂ 標記）
            if trend and total_now < int(trend[-1]["total_tokens"] or 0):
                reclaimed = int(trend[-1]["total_tokens"]) - total_now
                compact_count += 1
                marks.append({"kind": "compact", "label": f"reclaim:{reclaimed}"})
                insight_events.append(
                    {
                        "kind": "compact",
                        "event": "context_compact",
                        "seq": seq,
                        "ts": ts,
                        "producer": "heuristic",
                        "phase": ev.get("phase") or "",
                        "delta_tokens": -reclaimed,
                        "count": 1,
                        "summary": f"窗口收縮回收約 {reclaimed} tokens",
                    }
                )
            trend.append(
                {
                    "step": step_idx,
                    "seq": seq,
                    "ts": ts,
                    "phase": ev.get("phase") or "",
                    "role": ev.get("role") or "",
                    "model": ev.get("model"),
                    "total_tokens": total_now,
                    "bars": {k: int(snapshot[k]["tokens"]) for k in COMPOSITION_KEYS},
                    "delta_tokens": delta_tokens,
                    "delta_bars": {k: int(deltas.get(k) or 0) for k in COMPOSITION_KEYS},
                    "marks": marks,
                }
            )
            if cost_f:
                total_cost += cost_f
            if dur_f:
                total_duration_ms += dur_f
                duration_n += 1
            _touch_agent(str(ev.get("role") or "assistant"), tin=tin, tout=tout, cost=cost_f, dur=dur_f)

        elif et == "context_injection":
            items = ev.get("items") or []
            texts = [_item_text(x) for x in items]
            tok = sum(_est_tokens(t) for t in texts)
            inject_items_total += len(texts)
            _accumulate(running, {"injected": tok}, items={"injected": len(texts) or 1})
            insight_events.append(
                {
                    "kind": "inject",
                    "event": et,
                    "seq": seq,
                    "ts": ts,
                    "producer": ev.get("source") or "injection",
                    "phase": ev.get("phase") or "",
                    "delta_tokens": tok,
                    "count": ev.get("count") if ev.get("count") is not None else len(texts),
                    "summary": (ev.get("query") or texts[0] if texts else "")[:200],
                }
            )
            _mark("inject", str(ev.get("source") or "inject"))

        elif et == "memory_operation":
            memory_ops += 1
            detail = str(ev.get("text") or ev.get("detail") or ev.get("operation") or "")[:200]
            tok = _est_tokens(detail)
            op = str(ev.get("operation") or "").lower()
            kind = "inject" if op in {"add", "upsert", "write", "save"} else "prune"
            if kind == "prune":
                prune_count += 1
            insight_events.append(
                {
                    "kind": kind,
                    "event": et,
                    "seq": seq,
                    "ts": ts,
                    "producer": "memory",
                    "phase": ev.get("phase") or "",
                    "delta_tokens": tok if kind == "inject" else -tok,
                    "count": 1,
                    "summary": detail,
                }
            )
            _mark(kind, "memory")

        elif et == "phase_change":
            insight_events.append(
                {
                    "kind": "switch",
                    "event": et,
                    "seq": seq,
                    "ts": ts,
                    "producer": "orchestrator",
                    "phase": f"{ev.get('from_phase') or '?'}→{ev.get('to_phase') or ev.get('phase') or '?'}",
                    "delta_tokens": 0,
                    "count": 1,
                    "summary": str(ev.get("reason") or "")[:200],
                }
            )
            _mark("switch", "phase")

        elif et == "tool_call":
            tool_calls += 1
            name = str(ev.get("tool") or ev.get("name") or "tool")
            args_raw = ev.get("arguments") if ev.get("arguments") is not None else ev.get("args")
            args_s = args_raw if isinstance(args_raw, str) else str(args_raw or "")
            result_s = str(ev.get("result") or ev.get("output") or "")
            args_t = _est_tokens(args_s)
            result_t = _est_tokens(result_s)
            _accumulate(
                running,
                {"tools": args_t, "tool_results": result_t},
                items={"tools": 1, "tool_results": 1 if result_t else 0},
            )
            insight_events.append(
                {
                    "kind": "mode",
                    "event": et,
                    "seq": seq,
                    "ts": ts,
                    "producer": name,
                    "phase": ev.get("phase") or "",
                    "delta_tokens": args_t + result_t,
                    "count": 1,
                    "summary": name,
                }
            )
            tool_dur = ev.get("duration_ms")
            if isinstance(tool_dur, (int, float)):
                tool_duration_ms += float(tool_dur)
            purpose = _guess_file_purpose(name)
            if purpose:
                path = _extract_file_path(args_raw, result_s)
                added, removed = _line_delta(args_raw, result_s)
                hits = 1 if purpose == "searched" else 0
                if purpose == "searched" and isinstance(args_raw, dict):
                    raw_hits = args_raw.get("hits") or args_raw.get("count")
                    if isinstance(raw_hits, (int, float)):
                        hits = int(raw_hits)
                _touch_file(
                    path=path or name,
                    purpose=purpose,
                    tool=name,
                    seq=seq,
                    ts=ts,
                    added=added if purpose == "written" else 0,
                    removed=removed if purpose == "written" else 0,
                    hits=hits,
                )

        elif et in {"work_item_done", "seat_dispatch", "seat_result"}:
            role = str(ev.get("role") or ev.get("assignee") or ev.get("seat") or "").strip()
            if role and role not in agent_map:
                agent_map[role] = {
                    "role": role,
                    "llm_calls": 0,
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "cost": 0.0,
                    "duration_ms": 0.0,
                    "parent": ev.get("parent_role") or ev.get("parent"),
                }

    # 選定步驟
    selected_step = step
    if selected_step is None and llm_steps:
        selected_step = len(llm_steps) - 1
    selected = None
    if selected_step is not None and 0 <= selected_step < len(llm_steps):
        selected = llm_steps[selected_step]

    composition = selected["composition"] if selected else _normalize_shares(running)
    browser = _build_browser(selected, events, llm_steps) if selected else _build_browser_live(events, running)

    window_tokens = sum(int(composition[k]["tokens"]) for k in COMPOSITION_KEYS)
    # 粗略壓力：以 128k 為預設窗（可被前端覆蓋）
    default_window = 128_000
    pressure = min(1.0, window_tokens / default_window) if default_window else 0.0

    llm_ms = total_duration_ms
    overhead_ms = max(0.0, (llm_ms + tool_duration_ms) * 0.08)  # 固定比例估算編排開銷
    timing_total = llm_ms + tool_duration_ms + overhead_ms or 1.0

    file_activity = []
    for row in file_map.values():
        file_activity.append(
            {
                "path": row["path"],
                "purposes": sorted(row["purposes"]),
                "ops_count": len(row["ops"]),
                "added": row["added"],
                "removed": row["removed"],
                "hits": row["hits"],
                "last_seq": row["last_seq"],
                "last_ts": row["last_ts"],
                "ops": row["ops"][-12:],
            }
        )
    file_activity.sort(key=lambda r: (-r["ops_count"], r["path"]))

    agent_network = sorted(
        agent_map.values(),
        key=lambda r: (-(r["tokens_in"] + r["tokens_out"]), r["role"]),
    )
    # 主節點：呼叫最多者；其餘視為同族
    primary_role = agent_network[0]["role"] if agent_network else None
    for node in agent_network:
        if node.get("parent") is None and primary_role and node["role"] != primary_role:
            node["parent"] = primary_role

    stats = {
        "llm_calls": len(llm_steps),
        "context_injections": int(counts.get("context_injection") or 0),
        "memory_operations": memory_ops,
        "tool_calls": tool_calls,
        "phase_changes": int(counts.get("phase_change") or 0),
        "compacts": compact_count,
        "prunes": prune_count,
        "inject_items": inject_items_total,
        "est_window_tokens": window_tokens,
        "est_cost_usd": round(total_cost, 6),
        "avg_llm_ms": round(total_duration_ms / duration_n, 1) if duration_n else 0.0,
        "event_counts": counts,
        "context_pressure": round(pressure, 4),
        "context_window": default_window,
        "file_touches": len(file_activity),
        "agents": len(agent_network),
        "timing": {
            "llm_ms": round(llm_ms, 1),
            "tool_ms": round(tool_duration_ms, 1),
            "overhead_ms": round(overhead_ms, 1),
            "total_ms": round(timing_total, 1),
            "llm_share": round(llm_ms / timing_total, 4),
            "tool_share": round(tool_duration_ms / timing_total, 4),
            "overhead_share": round(overhead_ms / timing_total, 4),
        },
    }

    return {
        "task_id": task_id,
        "stats": stats,
        "composition": composition,
        "composition_keys": list(COMPOSITION_KEYS),
        "trend": trend,
        "events": insight_events[-200:],
        "steps": [
            {
                "step": s["step"],
                "seq": s["seq"],
                "ts": s["ts"],
                "model": s["model"],
                "phase": s["phase"],
                "role": s["role"],
                "prompt_tokens_est": s["prompt_tokens_est"],
                "completion_tokens_est": s["completion_tokens_est"],
            }
            for s in llm_steps
        ],
        "selected_step": selected_step,
        "browser": browser,
        "file_activity": file_activity,
        "agent_network": agent_network,
        "source": "trace",
        "heuristic": "chars_per_token=2",
    }


def _build_browser(
    step: dict[str, Any],
    events: list[dict[str, Any]],
    llm_steps: list[dict[str, Any]],
) -> dict[str, Any]:
    """選定步驟的 Context Browser 元素（含 vs 上一步 delta）。"""
    categories: dict[str, list[dict[str, Any]]] = {k: [] for k in COMPOSITION_KEYS}
    if step.get("system"):
        categories["system"].append(
            {
                "id": f"sys-{step['step']}",
                "label": "system prompt",
                "tokens": _est_tokens(step["system"]),
                "source": "llm_call",
                "content": step["system"],
            }
        )
    if step.get("prompt"):
        categories["user"].append(
            {
                "id": f"usr-{step['step']}",
                "label": "user / prompt",
                "tokens": _est_tokens(step["prompt"]),
                "source": step.get("role") or "prompt",
                "content": step["prompt"],
            }
        )
    # 彙入此步驟之前（含當步）的注入片段，方便瀏覽「注入上下文」
    step_seq = step.get("seq")
    for ev in events:
        if ev.get("event") != "context_injection":
            continue
        if step_seq is not None and ev.get("seq") is not None and int(ev["seq"]) > int(step_seq):
            continue
        for i, item in enumerate(ev.get("items") or []):
            text = _item_text(item)
            categories["injected"].append(
                {
                    "id": f"inj-{ev.get('seq')}-{i}",
                    "label": str(ev.get("source") or "injection"),
                    "tokens": _est_tokens(text),
                    "source": ev.get("source") or "injection",
                    "content": text[:2000],
                }
            )
    if step.get("response"):
        categories["assistant"].append(
            {
                "id": f"asst-{step['step']}",
                "label": "assistant reply",
                "tokens": _est_tokens(step["response"]),
                "source": step.get("model") or "assistant",
                "content": step["response"],
            }
        )
    # 工具綱要／結果（截至選定步驟）
    for ev in events:
        if ev.get("event") != "tool_call":
            continue
        if step_seq is not None and ev.get("seq") is not None and int(ev["seq"]) > int(step_seq):
            continue
        name = str(ev.get("tool") or ev.get("name") or "tool")
        args_raw = ev.get("arguments") if ev.get("arguments") is not None else ev.get("args")
        args = args_raw if isinstance(args_raw, str) else str(args_raw or "")
        result = str(ev.get("result") or ev.get("output") or "")
        if args:
            categories["tools"].append(
                {
                    "id": f"tool-{ev.get('seq')}",
                    "label": name,
                    "tokens": _est_tokens(args),
                    "source": _tool_source_chip(name),
                    "content": args[:2000],
                }
            )
        if result:
            categories["tool_results"].append(
                {
                    "id": f"tres-{ev.get('seq')}",
                    "label": f"{name} result",
                    "tokens": _est_tokens(result),
                    "source": _tool_source_chip(name),
                    "content": result[:2000],
                }
            )

    vs_previous = None
    idx = int(step["step"])
    if idx > 0 and idx < len(llm_steps):
        prev = llm_steps[idx - 1]["composition"]
        cur = step["composition"]
        vs_previous = {
            "prev_step": idx - 1,
            "deltas": {
                k: {
                    "tokens": int(cur[k]["tokens"]) - int(prev[k]["tokens"]),
                    "items": int(cur[k]["items"]) - int(prev[k]["items"]),
                }
                for k in COMPOSITION_KEYS
            },
        }

    return {
        "step": step["step"],
        "categories": categories,
        "vs_previous": vs_previous,
        "brief": {
            "user": (step.get("prompt") or "")[:160],
            "in": f"phase={step.get('phase') or '—'} · role={step.get('role') or '—'}",
            "response": (step.get("response") or "")[:160],
            "model": step.get("model") or "",
        },
    }


def _build_browser_live(events: list[dict[str, Any]], running: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """無 llm_call 時，以注入／工具事件組瀏覽器。"""
    categories: dict[str, list[dict[str, Any]]] = {k: [] for k in COMPOSITION_KEYS}
    for ev in events:
        et = ev.get("event")
        if et == "context_injection":
            for i, item in enumerate(ev.get("items") or []):
                text = _item_text(item)
                categories["injected"].append(
                    {
                        "id": f"inj-{ev.get('seq')}-{i}",
                        "label": str(ev.get("source") or "injection"),
                        "tokens": _est_tokens(text),
                        "source": ev.get("source") or "injection",
                        "content": text[:2000],
                    }
                )
        elif et == "tool_call":
            name = str(ev.get("tool") or ev.get("name") or "tool")
            args_raw = ev.get("arguments") if ev.get("arguments") is not None else ev.get("args")
            args = args_raw if isinstance(args_raw, str) else str(args_raw or "")
            result = str(ev.get("result") or ev.get("output") or "")
            if args:
                categories["tools"].append(
                    {
                        "id": f"tool-{ev.get('seq')}",
                        "label": name,
                        "tokens": _est_tokens(args),
                        "source": _tool_source_chip(name),
                        "content": args[:2000],
                    }
                )
            if result:
                categories["tool_results"].append(
                    {
                        "id": f"tres-{ev.get('seq')}",
                        "label": f"{name} result",
                        "tokens": _est_tokens(result),
                        "source": _tool_source_chip(name),
                        "content": result[:2000],
                    }
                )
    # 若完全空，放一筆佔位說明
    if not any(categories[k] for k in COMPOSITION_KEYS):
        categories["injected"].append(
            {
                "id": "empty",
                "label": "尚無上下文事件",
                "tokens": 0,
                "source": "system",
                "content": "等待任務產生 llm_call／context_injection 後即可瀏覽組成。",
            }
        )
    _ = running  # 保留簽名對齊
    return {"step": None, "categories": categories, "vs_previous": None, "brief": None}


def resolve_default_task_id(explicit: str | None = None) -> str | None:
    """解析預設任務：顯式 ID 優先，否則取最新軌跡。"""
    if explicit and explicit.strip():
        return explicit.strip()
    traces = list_traces(limit=1)
    if not traces:
        return None
    return str(traces[0].get("task_id") or "") or None
