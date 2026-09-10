"""阿里雲 BSS OpenAPI 接入（費用／用量）。

環境變數：
- ALIYUN_ACCESS_KEY_ID
- ALIYUN_ACCESS_KEY_SECRET
- ALIYUN_BSS_ENDPOINT（預設 business.aliyun.com）
- ALIYUN_CNY_USD_RATE（預設 0.14，用於將帳單 CNY 換算為 USD 納入 Agent 預算）

未配置憑證時回傳空帳目（configured=False），不阻斷本地 Docker 計費。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import time
import urllib.parse
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_ENDPOINT = "https://business.aliyun.com"
DEFAULT_CNY_USD = 0.14


def aliyun_configured() -> bool:
    return bool(os.getenv("ALIYUN_ACCESS_KEY_ID") and os.getenv("ALIYUN_ACCESS_KEY_SECRET"))


def _cny_to_usd(amount_cny: float) -> float:
    rate = float(os.getenv("ALIYUN_CNY_USD_RATE") or DEFAULT_CNY_USD)
    return round(amount_cny * rate, 6)


def _percent_encode(value: str) -> str:
    return urllib.parse.quote(str(value), safe="~")


def _sign(params: dict[str, str], secret: str) -> str:
    sorted_items = sorted(params.items())
    canonical = "&".join(f"{_percent_encode(k)}={_percent_encode(v)}" for k, v in sorted_items)
    string_to_sign = f"GET&%2F&{_percent_encode(canonical)}"
    digest = hmac.new(
        (secret + "&").encode("utf-8"),
        string_to_sign.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def _rpc_get(action: str, business: dict[str, str]) -> dict[str, Any]:
    """呼叫阿里雲 BSS RPC OpenAPI（SignatureVersion=1.0）。"""
    access_key = os.getenv("ALIYUN_ACCESS_KEY_ID", "")
    secret = os.getenv("ALIYUN_ACCESS_KEY_SECRET", "")
    endpoint = (os.getenv("ALIYUN_BSS_ENDPOINT") or DEFAULT_ENDPOINT).rstrip("/")
    if not endpoint.startswith("http"):
        endpoint = f"https://{endpoint}"

    params: dict[str, str] = {
        "Format": "JSON",
        "Version": "2017-12-14",
        "AccessKeyId": access_key,
        "SignatureMethod": "HMAC-SHA1",
        "Timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "SignatureVersion": "1.0",
        "SignatureNonce": str(uuid.uuid4()),
        "Action": action,
        **business,
    }
    params["Signature"] = _sign(params, secret)
    url = f"{endpoint}/?{urllib.parse.urlencode(params)}"
    with httpx.Client(timeout=12.0) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.json()


class AliyunBssClient:
    """查詢帳號帳單總覽與產品明細，換算為 USD。"""

    def __init__(self) -> None:
        self._cache: dict[str, Any] | None = None
        self._cache_at: float = 0.0
        self._cache_ttl = float(os.getenv("ALIYUN_BSS_CACHE_SEC") or 120)

    def get_billing_overview(self, force: bool = False) -> dict[str, Any]:
        """回傳統一結構，供 CloudBilling / Agent 預算合併。

        Returns:
            {
              configured, ok, currency, cny_usd_rate,
              month_total_cny, month_total_usd,
              today_total_cny, today_total_usd,
              products: [{product_code, product_name, pretax_amount_cny, cost_usd}],
              error
            }
        """
        now = time.time()
        if not force and self._cache is not None and (now - self._cache_at) < self._cache_ttl:
            return self._cache

        empty = {
            "configured": False,
            "ok": False,
            "currency": "CNY",
            "cny_usd_rate": float(os.getenv("ALIYUN_CNY_USD_RATE") or DEFAULT_CNY_USD),
            "month_total_cny": 0.0,
            "month_total_usd": 0.0,
            "today_total_cny": 0.0,
            "today_total_usd": 0.0,
            "products": [],
            "error": None,
            "billing_cycle": datetime.now(timezone.utc).strftime("%Y-%m"),
        }

        if not aliyun_configured():
            empty["error"] = "未配置 ALIYUN_ACCESS_KEY_ID / ALIYUN_ACCESS_KEY_SECRET"
            self._cache = empty
            self._cache_at = now
            return empty

        cycle = datetime.now(timezone.utc).strftime("%Y-%m")
        result = dict(empty)
        result["configured"] = True
        result["billing_cycle"] = cycle

        try:
            overview = _rpc_get(
                "QueryBillOverview",
                {"BillingCycle": cycle},
            )
            data = overview.get("Data") or overview.get("data") or {}
            items = data.get("Items") or data.get("items") or {}
            item_list = items.get("Item") or items.get("item") or []
            if isinstance(item_list, dict):
                item_list = [item_list]

            products: list[dict[str, Any]] = []
            month_cny = 0.0
            for raw in item_list:
                if not isinstance(raw, dict):
                    continue
                amount = float(
                    raw.get("PretaxAmount")
                    or raw.get("pretaxAmount")
                    or raw.get("PaymentAmount")
                    or 0
                )
                month_cny += amount
                code = str(raw.get("ProductCode") or raw.get("productCode") or "unknown")
                name = str(raw.get("ProductName") or raw.get("productName") or code)
                products.append(
                    {
                        "product_code": code,
                        "product_name": name,
                        "pretax_amount_cny": round(amount, 4),
                        "cost_usd": _cny_to_usd(amount),
                        "source": "aliyun",
                    }
                )

            # 若 Overview 無明細，改抓 AccountBill 合計
            if month_cny <= 0:
                account = _rpc_get(
                    "QueryAccountBill",
                    {
                        "BillingCycle": cycle,
                        "PageNum": "1",
                        "PageSize": "1",
                    },
                )
                adata = account.get("Data") or {}
                month_cny = float(adata.get("AccountAmount") or adata.get("TotalAmount") or 0)

            result["ok"] = True
            result["month_total_cny"] = round(month_cny, 4)
            result["month_total_usd"] = _cny_to_usd(month_cny)
            # 無日帳單 API 時以月額 / 當日比例粗估（監控展示用）
            day = datetime.now(timezone.utc).day
            days_in_month = 30
            today_cny = round(month_cny / max(days_in_month, day), 4)
            result["today_total_cny"] = today_cny
            result["today_total_usd"] = _cny_to_usd(today_cny)
            result["products"] = products
            result["error"] = None
        except Exception as exc:
            logger.warning("阿里雲 BSS 查詢失敗：%s", exc)
            result["ok"] = False
            result["error"] = str(exc)

        self._cache = result
        self._cache_at = now
        return result


_client: AliyunBssClient | None = None


def get_aliyun_bss() -> AliyunBssClient:
    global _client
    if _client is None:
        _client = AliyunBssClient()
    return _client


def reset_aliyun_bss() -> None:
    """測試用：清空單例。"""
    global _client
    _client = None
