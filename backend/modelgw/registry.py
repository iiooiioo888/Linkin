"""動態 Model Registry（Protocol + InMemory；SQL 見 sql_registry）。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Protocol


class ModelStatus(str, Enum):
    PENDING = "PENDING"
    PROVISIONING = "PROVISIONING"
    DOWNLOADING = "DOWNLOADING"
    LOADING = "LOADING"
    READY = "READY"
    FAILED = "FAILED"
    TERMINATING = "TERMINATING"


PROVISIONING_STATUSES = frozenset(
    {
        ModelStatus.PENDING,
        ModelStatus.PROVISIONING,
        ModelStatus.DOWNLOADING,
        ModelStatus.LOADING,
    }
)
NOT_READY_STATUSES = frozenset({ModelStatus.FAILED, ModelStatus.TERMINATING})


@dataclass
class ModelRecord:
    model_id: str
    revision: str
    endpoint: str = ""
    runtime: str = "cloud"
    provider: str = "cloud"
    gpu_type: str = ""
    lease_id: str = ""
    replicas: int = 1
    created_at: float = 0.0
    last_used_at: float = 0.0
    ttl: float | None = None
    status: ModelStatus = ModelStatus.READY
    # O18 相關欄位
    license: str = "Apache-2.0"
    trust_remote_code: bool = False
    gated: bool = False
    gated_approved: bool = False
    checksum: str | None = None  # 預留；PR1 可不驗
    plane: str = "cloud"  # local | cloud（Failover 形狀預留）
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value if isinstance(self.status, ModelStatus) else str(self.status)
        return d

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ModelRecord:
        data = dict(raw)
        status = data.get("status", ModelStatus.READY)
        if isinstance(status, str):
            status = ModelStatus(status.upper())
        data["status"] = status
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        extras = data.pop("extras", {}) or {}
        unknown = {k: data.pop(k) for k in list(data.keys()) if k not in known}
        extras = {**extras, **unknown}
        return cls(**data, extras=extras)


class Registry(Protocol):
    def get(self, model_id: str) -> ModelRecord | None: ...

    def upsert(self, record: ModelRecord) -> None: ...

    def ready(self) -> list[ModelRecord]: ...

    def ready_ids(self) -> list[str]: ...

    def all(self) -> list[ModelRecord]: ...


class InMemoryRegistry:
    """記憶體實作：pytest／無 DSN／顯式 MODELGW_REGISTRY_BACKEND=memory。"""

    def __init__(self, seed: list[ModelRecord] | None = None) -> None:
        self._items: dict[str, ModelRecord] = {}
        if seed:
            for rec in seed:
                self.upsert(rec)

    def get(self, model_id: str) -> ModelRecord | None:
        return self._items.get(model_id)

    def get_for_tenant(self, tenant_id: str, model_id: str) -> ModelRecord | None:
        """單平面：無租戶維度，語意等同 get（忽略 tenant_id）。隔離契約測走 SQL。"""
        _ = tenant_id
        return self.get(model_id)

    def upsert(self, record: ModelRecord) -> None:
        self._items[record.model_id] = record

    def ready(self) -> list[ModelRecord]:
        return [r for r in self._items.values() if r.status == ModelStatus.READY]

    def ready_ids(self) -> list[str]:
        return sorted(r.model_id for r in self.ready())

    def all(self) -> list[ModelRecord]:
        return list(self._items.values())

    def all_with_tenant(self) -> list[tuple[str, ModelRecord]]:
        """單平面：tenant_id 固定 ""。"""
        return [("", r) for r in self._items.values()]

    def clear(self) -> None:
        self._items.clear()


def load_json_seed(path: str | Path) -> list[ModelRecord]:
    """自 JSON 檔載入種子（測試／手動）。格式：{\"models\":[...]} 或 [...]。"""
    text = Path(path).read_text(encoding="utf-8")
    raw = json.loads(text)
    rows = raw["models"] if isinstance(raw, dict) and "models" in raw else raw
    if not isinstance(rows, list):
        raise ValueError("seed JSON 必須是 list 或 {models: list}")
    return [ModelRecord.from_dict(row) for row in rows]
