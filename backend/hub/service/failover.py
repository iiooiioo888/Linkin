"""Hub failover 設定解析與 messages 驗證（自 backend.hub.service 抽出）。"""

from __future__ import annotations

import json
from typing import Any

from backend.hub.catalog import HUB_CATALOG, is_forbidden_model_string
from backend.hub.errors import MSG_UNSUPPORTED, HubError


def parse_failover_config(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {
            "connect_timeout_ms": 25000,
            "read_timeout_ms": 120000,
            "max_retries": 3,
            "backoff_base": 2,
            "model_whitelist": None,
            "enable_race": False,
        }
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HubError(400, "BAD_REQUEST", "x-failover-config 不是合法 JSON") from exc
    if not isinstance(data, dict):
        raise HubError(400, "BAD_REQUEST", "x-failover-config 必須為物件")
    whitelist = data.get("model_whitelist")
    if whitelist is not None:
        if not isinstance(whitelist, list) or not (1 <= len(whitelist) <= 8):
            raise HubError(400, "BAD_REQUEST", "model_whitelist 長度須 1–8")
        cleaned: list[str] = []
        for item in whitelist:
            if not isinstance(item, str) or is_forbidden_model_string(item) or item not in HUB_CATALOG:
                raise HubError(400, "UNSUPPORTED_MODEL", MSG_UNSUPPORTED)
            cleaned.append(item)
        data["model_whitelist"] = cleaned
    data.setdefault("connect_timeout_ms", 25000)
    data.setdefault("read_timeout_ms", 120000)
    data.setdefault("enable_race", False)
    return data


def _validate_messages(messages: Any) -> list[dict[str, Any]]:
    """驗證聊天消息列表，加強輸入驗證。
    
    驗證規則：
    - 必須是非空列表
    - 最多 200 則消息
    - 每則消息必須包含 role 和 content
    - role 必須在允許的枚舉值中
    - content 不能為空或過長（最大 8000 字符）
    - 防止 XSS 和注入攻擊
    """
    import re
    
    if not isinstance(messages, list) or len(messages) == 0:
        raise HubError(400, "EMPTY_MESSAGES", "messages 不可為空")
    if len(messages) > 200:
        raise HubError(400, "BAD_REQUEST", "messages 最多 200 則")
    
    # 危險字符模式（防止腳本注入）
    dangerous_patterns = re.compile(r'<script[^>]*>|javascript:|on\w+\s*=', re.IGNORECASE)
    
    cleaned: list[dict[str, Any]] = []
    for idx, msg in enumerate(messages):
        if not isinstance(msg, dict):
            raise HubError(400, "BAD_REQUEST", f"第 {idx+1} 則消息必須為物件")
        if "role" not in msg or "content" not in msg:
            raise HubError(400, "BAD_REQUEST", f"第 {idx+1} 則消息缺少 role 或 content")
        
        role = msg["role"]
        if not isinstance(role, str):
            raise HubError(400, "BAD_REQUEST", f"第 {idx+1} 則消息的 role 必須為字符串")
        if role not in {"system", "user", "assistant", "tool"}:
            raise HubError(400, "BAD_REQUEST", f"第 {idx+1} 則消息的 role 不在允許範圍")
        
        content = msg["content"]
        if not isinstance(content, (str, list)):
            raise HubError(400, "BAD_REQUEST", f"第 {idx+1} 則消息的 content 格式錯誤")
        
        if isinstance(content, str):
            if not content.strip():
                raise HubError(400, "BLANK_CONTENT", f"第 {idx+1} 則消息的 content 不可全空白")
            if len(content) > 8000:
                raise HubError(400, "CONTENT_TOO_LONG", f"第 {idx+1} 則消息的 content 超過 8000 字符")
            # 檢查危險內容
            if dangerous_patterns.search(content):
                raise HubError(400, "DANGEROUS_CONTENT", f"第 {idx+1} 則消息包含不安全的內容")
        elif isinstance(content, list):
            # 多模態內容驗證
            if len(content) > 20:
                raise HubError(400, "BAD_REQUEST", f"第 {idx+1} 則消息的多模態內容過多")
            for item in content:
                if not isinstance(item, dict):
                    raise HubError(400, "BAD_REQUEST", f"第 {idx+1} 則消息的多模態項目必須為物件")
        
        cleaned.append({"role": role, "content": content})
    return cleaned
