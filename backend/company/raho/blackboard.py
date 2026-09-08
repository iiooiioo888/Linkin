"""共享記憶體（Blackboard）Schema：L2 ↔ L1 傳遞標準化。

未經 L1 簽核的條目不得被下游 L2 引用為已核准數據。
URI 一律使用 `shared_memory://` 指標，禁止把整份正文灌進原子角色。
"""

from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from backend.company.raho.protocol import RahoLayer

SCHEME = "shared_memory://"
RESULTS_PREFIX = f"{SCHEME}results/"
UPLOADS_PREFIX = f"{SCHEME}uploads/"
TICKET_URI = f"{SCHEME}l4/ticket.json"
UNSIGNED_WARNING = "警告：此指標尚未經 L1 簽核，禁止引用為已核准數據。"

_RESULT_NODE = re.compile(r"shared_memory://results/([^/_]+)")


@dataclass
class BlackboardEntry:
    """L1 簽核後才能標記 signed=True 的黑板條目。"""

    node_id: str
    uri: str
    data: Any = ""
    signature: str = ""
    inspector_id: str = ""
    quality_score: float = 0.0
    test_results: dict[str, str] = field(default_factory=dict)
    signed: bool = False
    layer: int = int(RahoLayer.L1_GRILL)
    title: str = ""
    created_at: float = 0.0
    verdict: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["created_at"] = self.created_at or time.time()
        return payload

    @classmethod
    def from_mapping(cls, raw: dict[str, Any] | None) -> "BlackboardEntry | None":
        if not isinstance(raw, dict) or not raw.get("node_id"):
            return None
        try:
            score = float(raw.get("quality_score") or 0)
        except (TypeError, ValueError):
            score = 0.0
        tests = raw.get("test_results") if isinstance(raw.get("test_results"), dict) else {}
        return cls(
            node_id=str(raw.get("node_id") or ""),
            uri=str(raw.get("uri") or result_uri(str(raw.get("node_id") or ""))),
            data=raw.get("data", ""),
            signature=str(raw.get("signature") or ""),
            inspector_id=str(raw.get("inspector_id") or ""),
            quality_score=score,
            test_results={str(k): str(v) for k, v in tests.items()},
            signed=bool(raw.get("signed")),
            layer=int(raw.get("layer") or RahoLayer.L1_GRILL),
            title=str(raw.get("title") or ""),
            created_at=float(raw.get("created_at") or 0),
            verdict=str(raw.get("verdict") or ""),
        )


def is_memory_uri(ref: Any) -> bool:
    return str(ref or "").strip().startswith(SCHEME)


def result_uri(node_id: str) -> str:
    key = (node_id or "").strip() or "unknown"
    return f"{RESULTS_PREFIX}{key}_output.json"


def upload_uri(name: str) -> str:
    file_name = (name or "payload.bin").strip().lstrip("/")
    return f"{UPLOADS_PREFIX}{file_name}"


def parse_node_id(ref: Any) -> str:
    text = str(ref or "").strip()
    if not text:
        return ""
    match = _RESULT_NODE.search(text)
    if match:
        return match.group(1)
    if text.startswith(RESULTS_PREFIX):
        tail = text[len(RESULTS_PREFIX):]
        return tail.replace("_output.json", "").split("/", 1)[0]
    if "/" in text:
        return text.rsplit("/", 1)[-1].replace("_output.json", "")
    return text


def signed_entry(
    *,
    node_id: str,
    data: Any,
    signature: str,
    inspector_id: str,
    quality_score: float,
    test_results: dict[str, str] | None = None,
    title: str = "",
    verdict: str = "APPROVED",
) -> dict[str, Any]:
    entry = BlackboardEntry(
        node_id=node_id,
        uri=result_uri(node_id),
        data=data,
        signature=signature,
        inspector_id=inspector_id,
        quality_score=quality_score,
        test_results=dict(test_results or {}),
        signed=True,
        layer=int(RahoLayer.L1_GRILL),
        title=title,
        created_at=time.time(),
        verdict=verdict,
    )
    return entry.to_dict()


__all__ = [
    "SCHEME",
    "RESULTS_PREFIX",
    "TICKET_URI",
    "UNSIGNED_WARNING",
    "UPLOADS_PREFIX",
    "BlackboardEntry",
    "is_memory_uri",
    "parse_node_id",
    "result_uri",
    "signed_entry",
    "upload_uri",
]
