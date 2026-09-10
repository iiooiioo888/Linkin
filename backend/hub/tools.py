"""工具執行層適配：五倉 GitHub 微服務契約。

StocksX / LittleCrawler / StoryForge 走沙箱 JSON（單元測試零外網）。
PysdnOPC_read 只模擬 opc_service REST 讀取形狀，禁止直連 OPC UA。
PysdnOPC_write 一律拒絕，必須由呼叫端走 opc_service + guard.py。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
from typing import Any
from uuid import uuid4

from backend.hub.errors import HubError

# JWT 密鑰：從環境變數讀取，若未設定則生成隨機密鑰（開發環境）
_jwt_secret_raw = os.getenv("JWT_SECRET", "").strip()
if not _jwt_secret_raw:
    # 開發環境：生成隨機密鑰並警告
    import secrets
    _jwt_secret_raw = secrets.token_hex(32)
    # 在生產環境中應該明確設定 JWT_SECRET
JWT_SECRET = _jwt_secret_raw.encode("utf-8") if isinstance(_jwt_secret_raw, str) else _jwt_secret_raw

STOCKSX_QUOTES: dict[str, dict[str, Any]] = {
    "600519": {
        "current_price": 1888,
        "pe_ratio": 28.5,
        "name": "貴州茅台",
        "currency": "CNY",
        "stale": False,
    },
    "600519.SH": {
        "current_price": 1888,
        "pe_ratio": 28.5,
        "name": "貴州茅台",
        "currency": "CNY",
        "stale": False,
    },
    "茅台": {
        "current_price": 1888,
        "pe_ratio": 28.5,
        "name": "貴州茅台",
        "currency": "CNY",
        "stale": False,
    },
}

# 爬蟲僅允許白名單 URL，禁止任意出站
CRAWLER_SANDBOX: dict[str, dict[str, Any]] = {
    "https://finance.example.com/600519": {
        "url": "https://finance.example.com/600519",
        "title": "貴州茅台估值快訊",
        "excerpt": "現價 1888 元，滾動 PE 28.5，成交量溫和放大。",
        "status": 200,
        "chars": 48,
    },
    "https://news.example.com/industry": {
        "url": "https://news.example.com/industry",
        "title": "製程感測週報",
        "excerpt": "本週鍋爐溫度均值 86.4°C，壓力穩定於 2.1 bar。",
        "status": 200,
        "chars": 42,
    },
}

OPC_SANDBOX: dict[str, dict[str, Any]] = {
    "Temperature": {"value": 86.4, "data_type": "Double", "quality": "Good"},
    "Pressure": {"value": 2.1, "data_type": "Double", "quality": "Good"},
    "FlowRate": {"value": 12.8, "data_type": "Double", "quality": "Good"},
    "ValvePosition": {"value": 45.0, "data_type": "Double", "quality": "Good"},
    "MotorSpeed": {"value": 1480, "data_type": "Int32", "quality": "Good"},
    "Level": {"value": 62.3, "data_type": "Double", "quality": "Good"},
    "AlarmStatus": {"value": 0, "data_type": "Boolean", "quality": "Good"},
    "PowerConsumption": {"value": 118.5, "data_type": "Double", "quality": "Good"},
}

_URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
_TAG_RE = re.compile(
    r"\b(Temperature|Pressure|FlowRate|ValvePosition|MotorSpeed|Level|AlarmStatus|PowerConsumption)\b"
)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def mint_tool_jwt(user_id: str, audience: str, scope: str, ttl_s: int = 60) -> str:
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    now = int(time.time())
    payload = {
        "iss": "ai-hub",
        "aud": audience,
        "sub": user_id,
        "scope": scope,
        "jti": uuid4().hex,
        "iat": now,
        "exp": now + ttl_s,
    }
    body = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(JWT_SECRET, f"{header}.{body}".encode(), hashlib.sha256).digest()
    return f"{header}.{body}.{_b64url(sig)}"


def verify_tool_jwt(token: str, audience: str, max_skew_s: int = 30) -> dict[str, Any]:
    try:
        header_b, body_b, sig_b = token.split(".")
    except ValueError as exc:
        raise HubError(502, "TOOL_AUTH_FAILED", "行情服務鑑權失敗，已中止以免提供過期數據。") from exc
    expected = _b64url(
        hmac.new(JWT_SECRET, f"{header_b}.{body_b}".encode(), hashlib.sha256).digest()
    )
    if not hmac.compare_digest(expected, sig_b):
        raise HubError(502, "TOOL_AUTH_FAILED", "行情服務鑑權失敗，已中止以免提供過期數據。")
    pad = "=" * (-len(body_b) % 4)
    payload = json.loads(base64.urlsafe_b64decode(body_b + pad))
    now = int(time.time())
    if payload.get("aud") != audience:
        raise HubError(502, "TOOL_AUTH_FAILED", "行情服務鑑權失敗，已中止以免提供過期數據。")
    if abs(now - int(payload.get("iat", 0))) > max_skew_s + 60:
        raise HubError(502, "TOOL_AUTH_FAILED", "行情服務鑑權失敗，已中止以免提供過期數據。")
    if int(payload.get("exp", 0)) < now - max_skew_s:
        raise HubError(502, "TOOL_AUTH_FAILED", "行情服務鑑權失敗，已中止以免提供過期數據。")
    return payload


def infer_symbol(user_input: str) -> str:
    text = user_input or ""
    if "茅台" in text or "600519" in text or "moutai" in text.lower():
        return "600519.SH"
    return "600519.SH"


def infer_url(user_input: str) -> str:
    text = user_input or ""
    match = _URL_RE.search(text)
    if match:
        return match.group(0).rstrip(".,;）)")
    if any(k in text for k in ("茅台", "估值", "股市", "股價")):
        return "https://finance.example.com/600519"
    return "https://news.example.com/industry"


def infer_opc_tags(user_input: str) -> list[str]:
    found = _TAG_RE.findall(user_input or "")
    if found:
        return list(dict.fromkeys(found))[:50]
    return ["Temperature", "Pressure", "FlowRate"]


def infer_genre(user_input: str) -> str:
    text = user_input or ""
    if any(k in text for k in ("科幻", "sci-fi", "星際")):
        return "scifi"
    if any(k in text for k in ("推理", "懸疑")):
        return "mystery"
    return "literary"


def infer_tools(user_input: str) -> list[str]:
    """依意圖自動掛載工具；金融場景維持 StocksX 為預設。"""
    text = user_input or ""
    tools: list[str] = []
    if any(k in text for k in ("茅台", "估值", "股市", "股價", "行情", "PE", "本益比")):
        tools.append("StocksX_get_price")
        if any(k in text for k in ("基本面", "ROE", "股息", "財報")):
            tools.append("StocksX_get_fundamentals")
    if any(k in text for k in ("爬", "抓取", "網頁", "新聞", "crawler", "http://", "https://")):
        tools.append("LittleCrawler_fetch")
    if any(k in text for k in ("故事", "小說", "創意", "劇本", "story")):
        tools.append("StoryForge_draft")
    if any(k in text for k in ("溫度", "壓力", "OPC", "閥", "工業", "感測", "製程")):
        tools.append("PysdnOPC_read")
    return tools


def tool_arguments(name: str, user_input: str) -> dict[str, Any]:
    if name.startswith("StocksX"):
        return {"symbol": infer_symbol(user_input)}
    if name == "LittleCrawler_fetch":
        return {"url": infer_url(user_input), "max_chars": 4000}
    if name == "StoryForge_draft":
        return {
            "premise": (user_input or "")[:500],
            "genre": infer_genre(user_input),
            "max_tokens": 800,
        }
    if name == "PysdnOPC_read":
        return {"tag_names": infer_opc_tags(user_input)}
    return {}


def stocksx_get_price(symbol: str, jwt: str) -> dict[str, Any]:
    verify_tool_jwt(jwt, audience="stocksx")
    quote = STOCKSX_QUOTES.get(symbol) or STOCKSX_QUOTES.get(symbol.replace(".SH", ""))
    if quote is None:
        raise HubError(400, "BAD_REQUEST", "symbol 不在行情白名單。")
    return dict(quote)


def stocksx_get_fundamentals(symbol: str, jwt: str) -> dict[str, Any]:
    quote = stocksx_get_price(symbol, jwt)
    quote["roe"] = 0.312
    quote["dividend_yield"] = 0.018
    quote["as_of"] = "2026-08-26T06:00:00Z"
    return quote


def littlecrawler_fetch(url: str, jwt: str, max_chars: int = 4000) -> dict[str, Any]:
    verify_tool_jwt(jwt, audience="littlecrawler")
    page = CRAWLER_SANDBOX.get(url)
    if page is None:
        raise HubError(400, "BAD_REQUEST", "URL 不在爬蟲白名單。")
    excerpt = page["excerpt"][: max(1, min(max_chars, 4000))]
    return {**page, "excerpt": excerpt, "stale": False}


def storyforge_draft(premise: str, jwt: str, genre: str = "literary") -> dict[str, Any]:
    verify_tool_jwt(jwt, audience="storyforge")
    seed = (premise or "未命名前提").strip()[:80]
    return {
        "title_candidates": [f"{seed}·序章", f"{seed}·迴聲"],
        "genre": genre,
        "outline": [
            {"beat": 1, "summary": "建立衝突與視角人物"},
            {"beat": 2, "summary": "情報反轉，迫使選擇"},
            {"beat": 3, "summary": "收束主題並留下餘韻"},
        ],
        "constraints": {"max_tokens": 800, "must_not_fabricate_facts": True},
    }


def pysdnopc_read(tag_names: list[str], jwt: str) -> dict[str, Any]:
    """模擬 POST http://opc_service:8001/opc/read，不直連 UA。"""
    verify_tool_jwt(jwt, audience="pysdnopc")
    if not tag_names or len(tag_names) > 50:
        raise HubError(400, "BAD_REQUEST", "tag_names 長度須 1–50")
    tags = []
    for name in tag_names:
        sample = OPC_SANDBOX.get(name)
        if sample is None:
            tags.append(
                {
                    "tag_name": name,
                    "value": None,
                    "data_type": "",
                    "quality": "Bad",
                }
            )
        else:
            tags.append({"tag_name": name, **sample})
    return {
        "via": "opc_service",
        "endpoint": "POST /opc/read",
        "guard_bypassed": False,
        "tags": tags,
        "error": None,
    }


def invoke_tool(name: str, user_input: str, user_id: str) -> dict[str, Any]:
    """同步呼叫工具。PysdnOPC_write 禁止在此直連 OPC UA。"""
    args = tool_arguments(name, user_input)
    if name == "PysdnOPC_write":
        raise HubError(
            400,
            "OPC_GUARD_REQUIRED",
            "工業寫入被安全護欄拒絕。",
        )
    if name == "PysdnOPC_read":
        token = mint_tool_jwt(user_id, "pysdnopc", "opc:read")
        data = pysdnopc_read(list(args.get("tag_names") or []), token)
        return {"tool": name, "arguments": args, "data": data, "http_status": 200}
    if name == "StocksX_get_price":
        token = mint_tool_jwt(user_id, "stocksx", "stocksx:read")
        data = stocksx_get_price(str(args["symbol"]), token)
        return {"tool": name, "arguments": args, "data": data, "http_status": 200}
    if name == "StocksX_get_fundamentals":
        token = mint_tool_jwt(user_id, "stocksx", "stocksx:read")
        data = stocksx_get_fundamentals(str(args["symbol"]), token)
        return {"tool": name, "arguments": args, "data": data, "http_status": 200}
    if name == "LittleCrawler_fetch":
        token = mint_tool_jwt(user_id, "littlecrawler", "crawler:read")
        data = littlecrawler_fetch(str(args["url"]), token, int(args.get("max_chars") or 4000))
        return {"tool": name, "arguments": args, "data": data, "http_status": 200}
    if name == "StoryForge_draft":
        token = mint_tool_jwt(user_id, "storyforge", "story:draft")
        data = storyforge_draft(str(args["premise"]), token, str(args.get("genre") or "literary"))
        return {"tool": name, "arguments": args, "data": data, "http_status": 200}
    raise HubError(400, "BAD_REQUEST", f"未知工具 {name}"[:80])
