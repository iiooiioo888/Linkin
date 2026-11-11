"""Context 洞察組成計算：token 估算、類別鍵、事件分類與檔案用途歸因 helper。"""

from __future__ import annotations

from typing import Any

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
    if low.startswith(("mcp_", "mcp:")) or "mcp/" in low:
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
