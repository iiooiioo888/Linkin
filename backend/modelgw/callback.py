"""部署完成回調：HMAC 驗簽＋冪等＋狀態單調寫入 Registry。

硬門：
- 僅用 ``MODELGW_CALLBACK_HMAC_KEY``（獨立；勿碰用戶側／guardrail HMAC）
- 不掛 AuthGate；不做 Bearer；本波不做公網 443
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from typing import Any

from backend.modelgw.registry import (
    PROVISIONING_STATUSES,
    ModelRecord,
    ModelStatus,
)
from backend.modelgw.sql_registry import SqliteRegistry

_PROVISIONING_VALUES = {s.value for s in PROVISIONING_STATUSES}


class CallbackError(Exception):
    """回調業務錯誤（對應 HTTP）。"""

    def __init__(
        self,
        message: str,
        *,
        code: str = "CALLBACK_ERROR",
        http_status: int = 400,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.http_status = http_status
        self.detail = message


class CallbackConflict(CallbackError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "CONFLICT",
        http_status: int = 409,
    ) -> None:
        super().__init__(message, code=code, http_status=http_status)


def callback_hmac_key() -> str:
    return (os.getenv("MODELGW_CALLBACK_HMAC_KEY") or "").strip()


def compute_request_hash(body: dict[str, Any]) -> str:
    """正規化 body JSON 後 SHA-256（穩定鍵序）。"""
    raw = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_signature_payload(
    body_bytes: bytes,
    *,
    timestamp: str | None = None,
    nonce: str | None = None,
) -> bytes:
    """HMAC 訊息：有 timestamp 時為 ``{ts}\\n{nonce}\\n`` + body；否則純 body。"""
    if timestamp:
        prefix = f"{timestamp}\n{nonce or ''}\n".encode()
        return prefix + body_bytes
    return body_bytes


def sign_body(
    body_bytes: bytes,
    key: str,
    *,
    timestamp: str | None = None,
    nonce: str | None = None,
) -> str:
    msg = build_signature_payload(body_bytes, timestamp=timestamp, nonce=nonce)
    digest = hmac.new(key.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_signature(
    body_bytes: bytes,
    signature_header: str | None,
    *,
    key: str | None = None,
    timestamp: str | None = None,
    nonce: str | None = None,
    max_skew_seconds: int = 300,
) -> None:
    """驗 ``X-ModelGW-Signature``；缺簽／錯簽 → CallbackError 401。"""
    secret = (key if key is not None else callback_hmac_key()).strip()
    if not secret:
        raise CallbackError(
            "MODELGW_CALLBACK_HMAC_KEY 未設定",
            code="CALLBACK_KEY_MISSING",
            http_status=503,
        )
    if not signature_header or not str(signature_header).strip():
        raise CallbackError(
            "缺少 X-ModelGW-Signature",
            code="SIGNATURE_REQUIRED",
            http_status=401,
        )
    header = str(signature_header).strip()
    if header.lower().startswith("sha256="):
        got = header.split("=", 1)[1].strip().lower()
    else:
        got = header.lower()
    expected_full = sign_body(body_bytes, secret, timestamp=timestamp, nonce=nonce)
    expected = expected_full.split("=", 1)[1].lower()
    if not hmac.compare_digest(got, expected):
        raise CallbackError(
            "HMAC 簽名不符",
            code="SIGNATURE_INVALID",
            http_status=401,
        )
    if timestamp:
        try:
            ts = float(timestamp)
        except ValueError as exc:
            raise CallbackError(
                "X-ModelGW-Timestamp 無效",
                code="TIMESTAMP_INVALID",
                http_status=401,
            ) from exc
        if abs(time.time() - ts) > max_skew_seconds:
            raise CallbackError(
                "時間戳超出允許偏移",
                code="TIMESTAMP_SKEW",
                http_status=401,
            )


def assert_status_transition(old_status: str, new_status: str) -> None:
    """狀態單調＋同態 LWW；非法 → CallbackConflict 409。

    P3/#132：
    - FAILED→READY（含超時後遲來 success）＝409 STATUS_TRANSITION_DENIED（G-P3-RACE1）
    - FAILED→PROVISIONING* 僅手動 outcome=reprovision（G-P3-RETRY1）
    """
    old = (old_status or "").upper()
    new = (new_status or "").upper()
    if old == new:
        return
    if old in _PROVISIONING_VALUES and new in _PROVISIONING_VALUES:
        return
    if old in _PROVISIONING_VALUES and new in {
        ModelStatus.READY.value,
        ModelStatus.FAILED.value,
        ModelStatus.TERMINATING.value,
    }:
        return
    if old == ModelStatus.READY.value and new == ModelStatus.TERMINATING.value:
        return
    # G-P3-RETRY1：FAILED → PROVISIONING*（僅 callback outcome=reprovision 會走到這）
    if old == ModelStatus.FAILED.value and new in _PROVISIONING_VALUES:
        return
    # 拒絕 READY→PROVISIONING*、TERMINATING→READY、FAILED→READY 等（含 RACE1）
    raise CallbackConflict(
        f"不允許的狀態轉換：{old} → {new}",
        code="STATUS_TRANSITION_DENIED",
        http_status=409,
    )


def resolve_target_status(body: dict[str, Any]) -> ModelStatus:
    """依 outcome／status 決定目標狀態。

    ``outcome=reprovision`` → PROVISIONING（G-P3-RETRY1；本波不另開 HTTP）。
    若同時帶顯式 status∈PROVISIONING*，以顯式為準。
    """
    explicit = str(body.get("status") or "").strip().upper()
    outcome = str(body.get("outcome") or "").strip().lower()
    if outcome == "reprovision":
        if explicit:
            try:
                st = ModelStatus(explicit)
            except ValueError as exc:
                raise CallbackError(
                    f"無效 status：{explicit}",
                    code="BAD_STATUS",
                    http_status=400,
                ) from exc
            if st.value in _PROVISIONING_VALUES:
                return st
            raise CallbackError(
                "outcome=reprovision 時 status 須為 PROVISIONING*",
                code="BAD_STATUS",
                http_status=400,
            )
        return ModelStatus.PROVISIONING
    if explicit:
        try:
            return ModelStatus(explicit)
        except ValueError as exc:
            raise CallbackError(
                f"無效 status：{explicit}",
                code="BAD_STATUS",
                http_status=400,
            ) from exc
    if outcome in {"success", "ok", "ready"}:
        return ModelStatus.READY
    if outcome in {"failure", "failed", "error"}:
        return ModelStatus.FAILED
    raise CallbackError(
        "需提供 outcome（success｜failure｜reprovision）或顯式 status",
        code="BAD_REQUEST",
        http_status=400,
    )


def body_to_record(
    body: dict[str, Any],
    *,
    target: ModelStatus,
    existing: ModelRecord | None = None,
    outcome: str = "",
) -> ModelRecord:
    model_id = str(body.get("model_id") or "").strip()
    if not model_id:
        raise CallbackError("缺少 model_id", code="BAD_REQUEST", http_status=400)
    revision = str(body.get("revision") or "").strip()
    if target == ModelStatus.READY and not revision:
        raise CallbackError(
            "success／READY 需 revision",
            code="BAD_REQUEST",
            http_status=400,
        )
    if not revision:
        revision = (existing.revision if existing and existing.revision else "unknown")
    raw_extras = body.get("extras")
    extras: dict[str, Any] = dict(raw_extras) if isinstance(raw_extras, dict) else {}
    if existing and isinstance(existing.extras, dict):
        # 既有 extras 為底；body extras／錯誤欄覆蓋
        extras = {**existing.extras, **extras}
    err_code = body.get("error_code")
    err_detail = body.get("error_detail")
    if err_code or err_detail:
        extras = {
            **extras,
            "error_code": err_code,
            "error_detail": err_detail,
        }

    from backend.modelgw.compensate import COMPENSATE_RETRYABLE
    from backend.modelgw.provision_controller import (
        EXTRA_COMPENSATE,
        EXTRA_FAIL_REASON,
        ensure_provision_started_at,
    )

    oc = (outcome or str(body.get("outcome") or "")).strip().lower()
    target_val = target.value if isinstance(target, ModelStatus) else str(target)

    if oc == "reprovision" or target_val in _PROVISIONING_VALUES:
        # G-P3-CLOCK1／RETRY1：reprovision 重置時鐘並清 fail／compensate
        force = oc == "reprovision"
        extras = ensure_provision_started_at(extras, force_reset=force)
        if force:
            extras.pop(EXTRA_FAIL_REASON, None)
            extras.pop(EXTRA_COMPENSATE, None)
            extras.pop("clock_backfill", None)
            extras.pop("error_code", None)
            extras.pop("error_detail", None)
    elif target == ModelStatus.FAILED:
        # 回調 failure：鎖 fail_reason＋補償可重跑
        if not extras.get(EXTRA_FAIL_REASON):
            extras[EXTRA_FAIL_REASON] = str(err_code or "callback_failure")
        extras[EXTRA_COMPENSATE] = COMPENSATE_RETRYABLE

    endpoint = str(body.get("endpoint") or "")
    if not endpoint and existing:
        endpoint = existing.endpoint or ""
    lease_id = str(body.get("lease_id") or "")
    if not lease_id and existing:
        lease_id = existing.lease_id or ""

    return ModelRecord(
        model_id=model_id,
        revision=revision,
        endpoint=endpoint,
        runtime=str(body.get("runtime") or (existing.runtime if existing else None) or "cloud"),
        provider=str(body.get("provider") or (existing.provider if existing else None) or "cloud"),
        gpu_type=str(body.get("gpu_type") or (existing.gpu_type if existing else None) or ""),
        lease_id=lease_id,
        replicas=int(body.get("replicas") or (existing.replicas if existing else None) or 1),
        created_at=float(body.get("created_at") or (existing.created_at if existing else 0.0) or 0.0),
        last_used_at=float(body.get("last_used_at") or 0.0),
        ttl=body.get("ttl") if "ttl" in body else (existing.ttl if existing else None),
        status=target,
        license=str(body.get("license") or (existing.license if existing else None) or "Apache-2.0"),
        trust_remote_code=bool(
            body.get("trust_remote_code", existing.trust_remote_code if existing else False)
        ),
        gated=bool(body.get("gated", existing.gated if existing else False)),
        gated_approved=bool(
            body.get("gated_approved", existing.gated_approved if existing else False)
        ),
        checksum=body.get("checksum") if "checksum" in body else (existing.checksum if existing else None),
        plane=str(body.get("plane") or (existing.plane if existing else None) or "cloud"),
        extras=extras,
    )


def process_deploy_callback(
    registry: SqliteRegistry,
    body: dict[str, Any],
    *,
    idempotency_key: str,
    body_bytes: bytes,
    signature_header: str | None,
    timestamp: str | None = None,
    nonce: str | None = None,
    hmac_key: str | None = None,
) -> dict[str, Any]:
    """完整回調處理：驗簽 → 冪等 → 寫入。回傳回應 JSON。"""
    if not idempotency_key or not str(idempotency_key).strip():
        raise CallbackError(
            "缺少 Idempotency-Key",
            code="IDEMPOTENCY_KEY_REQUIRED",
            http_status=400,
        )
    verify_signature(
        body_bytes,
        signature_header,
        key=hmac_key,
        timestamp=timestamp,
        nonce=nonce,
    )
    tenant_id = str(body.get("tenant_id") if body.get("tenant_id") is not None else "")
    target = resolve_target_status(body)
    outcome = str(body.get("outcome") or "").strip().lower()
    existing = registry.get_for_tenant(tenant_id, str(body.get("model_id") or "").strip())
    # G-P3-CLOCK1：同輪 PROVISIONING* 首次不覆蓋 provision_started_at（非 reprovision）
    record = body_to_record(body, target=target, existing=existing, outcome=outcome)
    req_hash = compute_request_hash(body)
    snapshot = {
        "ok": True,
        "idempotent_replay": False,
        "tenant_id": tenant_id,
        "model_id": record.model_id,
        "status": target.value,
        "row_version": 0,
    }
    return registry.apply_deploy_write(
        tenant_id=tenant_id,
        idempotency_key=str(idempotency_key).strip(),
        request_hash=req_hash,
        record=record,
        response_snapshot=snapshot,
        allow_create=True,
    )


__all__ = [
    "CallbackConflict",
    "CallbackError",
    "assert_status_transition",
    "body_to_record",
    "callback_hmac_key",
    "compute_request_hash",
    "process_deploy_callback",
    "sign_body",
    "verify_signature",
]
