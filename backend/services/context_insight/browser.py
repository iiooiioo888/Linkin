"""Context 洞察瀏覽器資料：browser 歷史／即時視圖與預設 task id 解析。"""

from __future__ import annotations

from typing import Any

from backend.services.trace_logger import list_traces

from .composition import COMPOSITION_KEYS, _est_tokens, _item_text, _tool_source_chip


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
