"""企業版私有授權 stub（節點 license key）。"""

from __future__ import annotations

import hashlib
import hmac
import os


def enterprise_license_configured() -> bool:
    return bool(os.getenv("LINKIN_ENTERPRISE_LICENSE", "").strip())


def validate_enterprise_license(license_key: str | None = None) -> bool:
    """校驗企業節點授權。未設定 LINKIN_ENTERPRISE_LICENSE 時 dev 模式放行。"""
    expected = os.getenv("LINKIN_ENTERPRISE_LICENSE", "").strip()
    if not expected:
        return True
    key = str(license_key or os.getenv("LINKIN_ENTERPRISE_LICENSE_KEY", "") or "").strip()
    if not key:
        return False
    digest = hmac.new(b"linkin.enterprise", key.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, expected)


def enterprise_status() -> dict:
    return {
        "license_required": enterprise_license_configured(),
        "license_valid": validate_enterprise_license(),
        "sso": {"enabled": False, "note": "MVP stub — SSO 介面待企業版整合"},
        "sla": {"tier": "custom", "note": "MVP stub — SLA 由合約定義"},
        "private_deploy": enterprise_license_configured(),
    }
