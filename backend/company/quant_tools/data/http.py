"""HTTP helper：共用 headers 與 JSON／text GET（_http_get_json／_http_get_text 為 patch 目標）。"""

from __future__ import annotations

from typing import Any

import httpx

from ..constants import _HTTP_TIMEOUT, _UA


def _http_headers() -> dict[str, str]:
    return {
        "User-Agent": _UA,
        "Accept": "application/json,text/csv,text/plain,*/*",
        "Referer": "https://finance.eastmoney.com/",
    }


def _http_get_json(url: str, params: dict[str, Any] | None = None) -> Any:
    with httpx.Client(timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
        resp = client.get(url, params=params, headers=_http_headers())
        resp.raise_for_status()
        return resp.json()


def _http_get_text(url: str, params: dict[str, Any] | None = None) -> str:
    with httpx.Client(timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
        resp = client.get(url, params=params, headers=_http_headers())
        resp.raise_for_status()
        return resp.text
