"""整合層基底：fail-open HTTP 客戶端＋審計軌跡＋路由原因碼。

設計要點：
- **fail-open**：連線失敗／逾時／非 2xx → ``ok=False``＋錯誤碼，呼叫方降級續跑。
- **可觀測**：每次呼叫留原因碼（``integration:<name>:<outcome>``）並可寫審計軌跡。
- **可測試**：``transport`` 可注入假實作，測試不依賴真實服務（AGENTS.md 約束 #2）。
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

logger = logging.getLogger(__name__)

ERR_INTEGRATION_DISABLED = "ERR_INTEGRATION_DISABLED"
ERR_INTEGRATION_UNREACHABLE = "ERR_INTEGRATION_UNREACHABLE"
ERR_INTEGRATION_BAD_RESPONSE = "ERR_INTEGRATION_BAD_RESPONSE"

# transport 型別：(method, url, headers, body_bytes, timeout) -> (status, body_bytes)
Transport = Callable[[str, str, Mapping[str, str], bytes | None, float], tuple[int, bytes]]


def _urllib_transport(
    method: str, url: str, headers: Mapping[str, str], body: bytes | None, timeout: float
) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=body, headers=dict(headers), method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — 僅內網自建服務
        return resp.status, resp.read()


@dataclass(frozen=True)
class IntegrationConfig:
    """單一外部服務的連線設定。"""

    name: str                      # memos / openviking / weknora / yao
    base_url: str                  # e.g. http://localhost:8000
    enabled: bool = False          # 預設關閉：啟用必須是顯式動作
    api_key: str = ""
    timeout_seconds: float = 5.0
    extra_headers: Mapping[str, str] = field(default_factory=dict)


@dataclass
class IntegrationResponse:
    """統一回應封套：永遠不拋例外（fail-open）。"""

    ok: bool
    data: Any = None
    error_code: str = ""
    reason_code: str = ""
    latency_ms: float = 0.0


@dataclass
class ResilientHttpClient:
    """fail-open JSON HTTP 客戶端。

    - ``trail``：可選的 ``(event: dict) -> None``，呼叫記錄寫入審計軌跡（C-AUDIT-005）。
    - ``transport``：可注入，預設 urllib；測試注入假 transport。
    - ``sleep``：可注入假時鐘。
    """

    config: IntegrationConfig
    transport: Transport = _urllib_transport
    trail: Callable[[dict], None] | None = None
    clock: Callable[[], float] = time.monotonic

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", **self.config.extra_headers}
        if self.config.api_key:
            headers.setdefault("Authorization", f"Token {self.config.api_key}")
        return headers

    def request(self, method: str, path: str, payload: dict | None = None) -> IntegrationResponse:
        name = self.config.name
        if not self.config.enabled:
            return self._finish(False, None, ERR_INTEGRATION_DISABLED, f"integration:{name}:disabled", 0.0, method, path)
        url = f"{self.config.base_url.rstrip('/')}/{path.lstrip('/')}"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        started = self.clock()
        try:
            status, raw = self.transport(method, url, self._headers(), body, self.config.timeout_seconds)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            latency = (self.clock() - started) * 1000
            logger.warning("整合 %s 不可達（fail-open）：%s", name, exc)
            return self._finish(False, None, ERR_INTEGRATION_UNREACHABLE, f"integration:{name}:unreachable", latency, method, path)
        latency = (self.clock() - started) * 1000
        if status >= 400:
            return self._finish(False, None, ERR_INTEGRATION_BAD_RESPONSE, f"integration:{name}:http_{status}", latency, method, path)
        try:
            data = json.loads(raw.decode("utf-8")) if raw else None
        except (ValueError, UnicodeDecodeError):
            return self._finish(False, None, ERR_INTEGRATION_BAD_RESPONSE, f"integration:{name}:bad_json", latency, method, path)
        return self._finish(True, data, "", f"integration:{name}:ok", latency, method, path)

    def get(self, path: str) -> IntegrationResponse:
        return self.request("GET", path)

    def post(self, path: str, payload: dict | None = None) -> IntegrationResponse:
        return self.request("POST", path, payload)

    def _finish(
        self,
        ok: bool,
        data: Any,
        error_code: str,
        reason_code: str,
        latency_ms: float,
        method: str,
        path: str,
    ) -> IntegrationResponse:
        if self.trail is not None:
            self.trail(
                {
                    "type": "integration_call",
                    "integration": self.config.name,
                    "method": method,
                    "path": path,
                    "ok": ok,
                    "error_code": error_code,
                    "reason_code": reason_code,
                    "latency_ms": round(latency_ms, 2),
                }
            )
        return IntegrationResponse(
            ok=ok, data=data, error_code=error_code, reason_code=reason_code, latency_ms=latency_ms
        )
