"""READY 閘 + O18 準入策略（PR1：allowlist + trc 預設拒 + revision 禁 main + gated 骨架）。"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from backend.modelgw.errors import (
    CODE_ADMISSION,
    CODE_NOT_READY,
    CODE_PROVISIONING,
    CODE_UNSUPPORTED,
    REASON_GATE,
    REASON_LICENSE,
    REASON_REVISION_MAIN,
    REASON_TRC,
)
from backend.modelgw.registry import (
    NOT_READY_STATUSES,
    PROVISIONING_STATUSES,
    ModelRecord,
    ModelStatus,
    Registry,
)

# 授權 allowlist（其餘人工審批 → PR1 直接拒）
DEFAULT_LICENSE_ALLOWLIST: frozenset[str] = frozenset(
    {
        "Apache-2.0",
        "MIT",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "BSD",
        "CC0-1.0",
        "ISC",
        "Unlicense",
    }
)


class AdmitDecision(str, Enum):
    ALLOW = "ALLOW"
    REJECT = "REJECT"
    PROVISIONING = "PROVISIONING"


@dataclass(frozen=True)
class AdmitResult:
    decision: AdmitDecision
    code: str | None = None
    reason: str | None = None
    record: ModelRecord | None = None

    @property
    def allowed(self) -> bool:
        return self.decision == AdmitDecision.ALLOW

    @classmethod
    def allow(cls, record: ModelRecord) -> AdmitResult:
        return cls(AdmitDecision.ALLOW, record=record)

    @classmethod
    def reject(cls, code: str, reason: str | None = None) -> AdmitResult:
        return cls(AdmitDecision.REJECT, code=code, reason=reason)

    @classmethod
    def provisioning(cls, record: ModelRecord | None = None) -> AdmitResult:
        return cls(AdmitDecision.PROVISIONING, code=CODE_PROVISIONING, record=record)


@dataclass
class AdmissionPolicy:
    """O18 PR1 策略。checksum 欄位預留、可不驗。"""

    license_allowlist: frozenset[str] = DEFAULT_LICENSE_ALLOWLIST
    allow_trust_remote_code: bool = False  # 預設拒絕
    ban_revision_main: bool = True
    require_gated_approval: bool = True
    verify_checksum: bool = False  # PR1 跳過

    def evaluate_o18(self, record: ModelRecord) -> AdmitResult | None:
        """回傳 Reject 或 None（通過）。"""
        lic = (record.license or "").strip()
        if lic not in self.license_allowlist:
            return AdmitResult.reject(CODE_ADMISSION, REASON_LICENSE)

        if record.trust_remote_code and not self.allow_trust_remote_code:
            return AdmitResult.reject(CODE_ADMISSION, REASON_TRC)

        rev = (record.revision or "").strip()
        if not rev:
            return AdmitResult.reject(CODE_ADMISSION, REASON_REVISION_MAIN)
        if self.ban_revision_main and rev.lower() in {"main", "master"}:
            return AdmitResult.reject(CODE_ADMISSION, REASON_REVISION_MAIN)

        if self.require_gated_approval and record.gated and not record.gated_approved:
            return AdmitResult.reject(CODE_ADMISSION, REASON_GATE)

        # checksum 預留：verify_checksum=True 時才檢查
        if self.verify_checksum and not (record.checksum or "").strip():
            from backend.modelgw.errors import REASON_CHECKSUM

            return AdmitResult.reject(CODE_ADMISSION, REASON_CHECKSUM)

        return None


_DEFAULT_POLICY = AdmissionPolicy()


def admit(
    model_id: str,
    registry: Registry,
    policy: AdmissionPolicy | None = None,
) -> AdmitResult:
    """路由熱路徑準入：missing → UNSUPPORTED；部署中 → PROVISIONING；FAILED → NOT_READY；再 O18。"""
    pol = policy or _DEFAULT_POLICY
    record = registry.get(model_id)
    if record is None:
        return AdmitResult.reject(CODE_UNSUPPORTED)

    status = record.status
    if isinstance(status, str):
        status = ModelStatus(status.upper())

    if status in PROVISIONING_STATUSES:
        return AdmitResult.provisioning(record)

    if status in NOT_READY_STATUSES:
        return AdmitResult.reject(CODE_NOT_READY)

    if status != ModelStatus.READY:
        return AdmitResult.reject(CODE_NOT_READY)

    denied = pol.evaluate_o18(record)
    if denied is not None:
        return denied

    return AdmitResult.allow(record)


def filter_admitted(
    model_ids: Iterable[str],
    registry: Registry,
    policy: AdmissionPolicy | None = None,
) -> list[str]:
    """回傳通過準入的 model_id 列表（順序保留）。"""
    out: list[str] = []
    for mid in model_ids:
        r = admit(mid, registry, policy)
        if r.allowed:
            out.append(mid)
    return out
