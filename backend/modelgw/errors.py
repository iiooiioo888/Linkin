"""ModelGW 錯誤碼（庫層；日後 HTTP 映射見 gap §8.1）。"""

from __future__ import annotations

from typing import Any


class ModelGWError(Exception):
    """可轉成 problem+json 的業務錯誤。

    日後掛 HTTP：
    - PROVISIONING → 503 + code=PROVISIONING（可選 Retry-After）
    - UNSUPPORTED_MODEL / ADMISSION_REJECTED / MODEL_NOT_READY → 400 + body code
    拒用 202／409／425。
    """

    def __init__(
        self,
        code: str,
        detail: str,
        *,
        reason: str | None = None,
        http_hint: int | None = None,
    ) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail[:120]
        self.reason = reason
        self.http_hint = http_hint

    def to_problem(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "type": f"https://modelgw.example.com/errors/{self.code}",
            "title": self.code.replace("_", " ").title(),
            "code": self.code,
            "detail": self.detail,
        }
        if self.reason:
            body["reason"] = self.reason
        if self.http_hint is not None:
            body["status"] = self.http_hint
        return body


CODE_UNSUPPORTED = "UNSUPPORTED_MODEL"
CODE_PROVISIONING = "PROVISIONING"
CODE_NOT_READY = "MODEL_NOT_READY"
CODE_ADMISSION = "ADMISSION_REJECTED"
CODE_ALL_OPEN = "ALL_CANDIDATES_OPEN"
CODE_UPSTREAM = "UPSTREAM_FAILED"

# O18 reason 子碼
REASON_LICENSE = "LICENSE_NOT_ALLOWED"
REASON_TRC = "TRUST_REMOTE_CODE_DENIED"
REASON_REVISION_MAIN = "REVISION_MAIN_FORBIDDEN"
REASON_GATE = "GATE_REQUIRED"
REASON_CHECKSUM = "CHECKSUM_MISSING"  # 預留；PR1 不驗
