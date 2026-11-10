"""Media Vault 領域列舉與風險推導。"""

from __future__ import annotations

COMPLIANCE_VALUES = frozenset(
    {
        "public",
        "licensed",
        "internal",
        "unknown",
        "restricted",
        "prohibited",
    }
)

RISK_LEVELS = frozenset({"green", "yellow", "red"})

_MEDIA_KINDS = frozenset({"original", "thumb_300", "thumb_800"})


def risk_level_from_compliance(compliance_basis: str) -> str:
    basis = (compliance_basis or "unknown").strip().lower()
    if basis in {"public", "licensed"}:
        return "green"
    if basis in {"restricted", "prohibited"}:
        return "red"
    return "yellow"


def normalize_compliance(raw: str | None) -> str:
    val = (raw or "unknown").strip().lower()
    return val if val in COMPLIANCE_VALUES else "unknown"


def normalize_media_kind(raw: str) -> str:
    val = raw.strip().lower()
    if val in _MEDIA_KINDS:
        return val
    raise ValueError(f"unknown media kind: {raw}")
