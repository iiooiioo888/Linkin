"""實驗室整合工具 — Firecrawl / Prompt Optimizer / Ponytail / Archify。

Firecrawl：可選 FIRECRAWL_API_KEY，未設定時走 httpx 輕量抓取。
Prompt Optimizer / Ponytail：經 call_llm，遵守 AGENTS.md LLM 抽象層約束。
Archify：以 tt-a1i/archify CLI 把 IR 編成獨立 HTML；前端 iframe 嵌入。
"""

from __future__ import annotations

import json
import os
import re
from html import unescape
from typing import Any
from urllib.parse import urlparse

import httpx

from backend.core.llm import call_llm

FIRECRAWL_API_BASE = "https://api.firecrawl.dev/v2"
_HTTP_TIMEOUT = 20.0
_MAX_BODY_CHARS = 120_000

PROMPT_OPTIMIZER_SYSTEM = """你是 Prompt Optimizer 助手（參考 linshenkx/prompt-optimizer）。
任務：將使用者提供的提示詞改寫為更清晰、可執行、可評估的版本。

規則：
1. 保留原意，不添加未請求的功能或假設。
2. 結構化：角色 → 約束 → 輸出格式 → 邊界條件。
3. 移除冗語、模糊詞與互相矛盾的指令。
4. 若為 system 模式，聚焦行為與邊界；若為 user 模式，聚焦任務與上下文佔位符。
5. 只輸出優化後的提示詞正文，不要解釋。"""

PONYTAIL_REVIEW_SYSTEM = """你是 Ponytail 程式碼審查助手（參考 DietrichGebert/ponytail）。
審查輸入是否過度工程化，並給出可刪除清單。

階梯（停在第一個夠用的梯級）：
1. 是否需要存在？（YAGNI）
2. 程式庫內是否已有可重用？
3. 標準庫是否已涵蓋？
4. 平台原生功能是否足夠？
5. 已安裝依賴是否可解？
6. 能否一行搞定？
7. 最後才寫最小可用實作。

不可刪：信任邊界驗證、防資料遺失的錯誤處理、安全、無障礙、使用者明確要求的功能。

以 JSON 回覆（不要 markdown 圍欄）：
{
  "summary": "一句話結論",
  "severity": "low|medium|high",
  "delete_list": ["可刪除或簡化的項目"],
  "keep_list": ["必須保留的項目"],
  "suggested_rewrite": "更精簡的替代方案（可選）"
}"""

ARCHIFY_GENERATE_SYSTEM = """你是 Archify 架構圖助手（參考 tt-a1i/archify）。
根據描述產出 architecture 類型的 JSON IR。

只輸出 JSON（不要 markdown 圍欄），格式：
{
  "meta": {"title": "標題", "type": "architecture", "locale": "zh-TW"},
  "nodes": [{"id": "唯一id", "label": "顯示名", "role": "frontend|api|service|data|external"}],
  "edges": [{"from": "源id", "to": "目標id", "label": "可選關係"}]
}

節點 6–12 個，一條主路徑，其餘細節放節點 label，不要發明不存在的元件。"""

EVOLOOP_ARCHITECTURE_IR: dict[str, Any] = {
    "meta": {
        "title": "EvoLoop 統一管線",
        "type": "architecture",
        "locale": "zh-TW",
        "source": "archify",
    },
    "nodes": [
        {"id": "ui", "label": "前端 · React/Vite", "role": "frontend"},
        {"id": "api", "label": "FastAPI 後端", "role": "api"},
        {"id": "router", "label": "route_by_complexity", "role": "service"},
        {"id": "graph", "label": "LangGraph 反思閉環", "role": "service"},
        {"id": "company", "label": "公司運行時 · 多代理人", "role": "service"},
        {"id": "opc", "label": "OPC 微服務 · guard", "role": "service"},
        {"id": "llm", "label": "LiteLLM 統一層", "role": "external"},
        {"id": "redis", "label": "Redis", "role": "data"},
        {"id": "chroma", "label": "ChromaDB 向量記憶", "role": "data"},
    ],
    "edges": [
        {"from": "ui", "to": "api", "label": "REST / WS"},
        {"from": "api", "to": "router", "label": "任務路由"},
        {"from": "router", "to": "graph", "label": "簡單任務"},
        {"from": "router", "to": "company", "label": "複雜任務"},
        {"from": "router", "to": "opc", "label": "工業 OPC"},
        {"from": "graph", "to": "llm", "label": "call_llm"},
        {"from": "company", "to": "llm", "label": "call_llm"},
        {"from": "opc", "to": "llm", "label": "診斷/決策"},
        {"from": "graph", "to": "chroma", "label": "記憶檢索"},
        {"from": "api", "to": "redis", "label": "快取/廣播"},
    ],
}


def _strip_html(html: str) -> str:
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", "\n", text)
    text = unescape(text)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines)


def _basic_scrape(url: str) -> dict[str, Any]:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("僅支援 http/https URL")
    with httpx.Client(timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
        resp = client.get(url, headers={"User-Agent": "EvoLoop-Lab/1.0"})
        resp.raise_for_status()
        body = resp.text[:_MAX_BODY_CHARS]
    title_match = re.search(r"(?is)<title[^>]*>(.*?)</title>", body)
    title = unescape(title_match.group(1).strip()) if title_match else parsed.netloc
    markdown = _strip_html(body)
    return {
        "url": url,
        "title": title,
        "markdown": markdown[:8000],
        "source": "basic",
        "status": 200,
    }


def firecrawl_scrape(url: str, only_main_content: bool = True) -> dict[str, Any]:
    """抓取單頁；有 FIRECRAWL_API_KEY 時走官方 API，否則 httpx 輕量抓取。"""
    api_key = os.getenv("FIRECRAWL_API_KEY", "").strip()
    if not api_key:
        data = _basic_scrape(url)
        data["hint"] = "未設定 FIRECRAWL_API_KEY，已使用輕量抓取。設定後可取得 JS 渲染與更乾淨的 Markdown。"
        return data

    payload: dict[str, Any] = {
        "url": url,
        "formats": ["markdown"],
        "onlyMainContent": only_main_content,
    }
    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        resp = client.post(
            f"{FIRECRAWL_API_BASE}/scrape",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        body = resp.json()

    raw_data = body.get("data") if isinstance(body, dict) else None
    page_data: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}
    markdown = page_data.get("markdown") or page_data.get("content") or ""
    raw_metadata = page_data.get("metadata")
    metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
    return {
        "url": metadata.get("sourceURL") or metadata.get("url") or url,
        "title": metadata.get("title") or url,
        "markdown": str(markdown)[:8000],
        "source": "firecrawl",
        "status": 200,
    }


def firecrawl_search(query: str, limit: int = 5) -> dict[str, Any]:
    """搜尋網頁；需 FIRECRAWL_API_KEY。"""
    api_key = os.getenv("FIRECRAWL_API_KEY", "").strip()
    if not api_key:
        return {
            "query": query,
            "results": [],
            "source": "none",
            "hint": "搜尋需設定 FIRECRAWL_API_KEY。單頁抓取可在無金鑰時使用輕量模式。",
        }

    limit = max(1, min(limit, 10))
    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        resp = client.post(
            f"{FIRECRAWL_API_BASE}/search",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={"query": query, "limit": limit},
        )
        resp.raise_for_status()
        body = resp.json()

    raw = body.get("data") if isinstance(body, dict) else body
    results: list[dict[str, Any]] = []
    if isinstance(raw, list):
        for item in raw[:limit]:
            if not isinstance(item, dict):
                continue
            results.append(
                {
                    "url": item.get("url") or "",
                    "title": item.get("title") or item.get("url") or "",
                    "markdown": str(item.get("markdown") or item.get("description") or "")[:2000],
                }
            )
    return {"query": query, "results": results, "source": "firecrawl"}


def optimize_prompt(prompt: str, mode: str = "user", goal: str = "") -> dict[str, Any]:
    """Prompt Optimizer — 經 LLM 改寫提示詞。"""
    text = (prompt or "").strip()
    if not text:
        raise ValueError("提示詞不可為空")
    mode_norm = "system" if mode == "system" else "user"
    user = f"模式：{mode_norm}\n"
    if goal.strip():
        user += f"優化目標：{goal.strip()}\n"
    user += f"\n原始提示詞：\n{text}"
    optimized = call_llm(user, system=PROMPT_OPTIMIZER_SYSTEM, max_retries=1).strip()
    return {
        "original": text,
        "optimized": optimized,
        "mode": mode_norm,
        "source": "prompt-optimizer",
    }


def _parse_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("回應不是 JSON 物件")
    return parsed


def ponytail_review(content: str, kind: str = "code") -> dict[str, Any]:
    """Ponytail 過度工程審查。"""
    text = (content or "").strip()
    if not text:
        raise ValueError("審查內容不可為空")
    kind_norm = kind if kind in ("code", "prompt", "diff") else "code"
    user = f"審查類型：{kind_norm}\n\n{text[:12000]}"
    raw = call_llm(user, system=PONYTAIL_REVIEW_SYSTEM, max_retries=1)
    try:
        data = _parse_json_object(raw)
    except (json.JSONDecodeError, ValueError):
        data = {
            "summary": raw[:500],
            "severity": "medium",
            "delete_list": [],
            "keep_list": [],
            "suggested_rewrite": "",
        }
    return {
        "kind": kind_norm,
        "review": data,
        "source": "ponytail",
    }


def get_evoloop_architecture() -> dict[str, Any]:
    return dict(EVOLOOP_ARCHITECTURE_IR)


def generate_architecture(description: str) -> dict[str, Any]:
    """Archify — 由描述生成 architecture IR。"""
    desc = (description or "").strip()
    if not desc:
        raise ValueError("描述不可為空")
    raw = call_llm(desc, system=ARCHIFY_GENERATE_SYSTEM, max_retries=1)
    try:
        ir = _parse_json_object(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"無法解析架構 IR：{exc}") from exc
    if "nodes" not in ir or "edges" not in ir:
        raise ValueError("IR 缺少 nodes 或 edges")
    ir.setdefault("meta", {"title": desc[:40], "type": "architecture", "locale": "zh-TW"})
    ir["meta"]["source"] = "archify"
    return ir
