"""P0-11：模型註冊與執行前校驗。"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.local_video_studio.models import ModelRegistry
from backend.local_video_studio.schemas import ModelRegister, ModelRegistryOut


class ModelValidationError(ValueError):
    """缺模型或 VAE 不相容；訊息須含模型名。"""


_VAE_WAN21 = re.compile(r"wan[_\-]?2\.?1[_\-]?vae", re.IGNORECASE)
_VAE_WAN22 = re.compile(r"wan2\.?2[_\-]?vae", re.IGNORECASE)
_NAME_5B = re.compile(r"(?:^|[\-_])5b(?:$|[\-_])|wan.?2\.2.?5b", re.IGNORECASE)
_NAME_14B = re.compile(r"(?:^|[\-_])14b(?:$|[\-_])|wan.?2\.1.?14b|wan.?14b", re.IGNORECASE)


def _to_out(row: ModelRegistry) -> ModelRegistryOut:
    return ModelRegistryOut(
        id=row.id,
        name=row.name,
        path=row.path,
        sha256=row.sha256,
        vae_name=row.vae_name,
        notes=row.notes,
        created_at=row.created_at,
    )


def register_model(session: Session, body: ModelRegister) -> ModelRegistryOut:
    name = (body.name or "").strip()
    path = (body.path or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="模型名不可為空")
    if not path:
        raise HTTPException(status_code=422, detail="模型路徑不可為空")

    existing = session.scalar(select(ModelRegistry).where(ModelRegistry.name == name))
    if existing is not None:
        existing.path = path
        existing.sha256 = body.sha256
        existing.vae_name = body.vae_name
        existing.notes = body.notes
        session.flush()
        return _to_out(existing)

    row = ModelRegistry(
        name=name,
        path=path,
        sha256=body.sha256,
        vae_name=body.vae_name,
        notes=body.notes,
    )
    session.add(row)
    session.flush()
    return _to_out(row)


def list_models(session: Session) -> list[ModelRegistryOut]:
    rows = session.scalars(select(ModelRegistry).order_by(ModelRegistry.name.asc())).all()
    return [_to_out(r) for r in rows]


def get_model(session: Session, name: str) -> ModelRegistryOut:
    row = session.scalar(select(ModelRegistry).where(ModelRegistry.name == name))
    if row is None:
        raise HTTPException(status_code=404, detail=f"模型未註冊：{name}")
    return _to_out(row)


def _check_vae_compatibility(model_name: str, vae_name: str | None) -> None:
    if not vae_name:
        return
    vae = vae_name.strip()
    is_5b = bool(_NAME_5B.search(model_name))
    is_14b = bool(_NAME_14B.search(model_name))
    if is_5b and _VAE_WAN21.search(vae):
        raise ModelValidationError(
            f"VAE 不可混用：模型 {model_name}（Wan 5B）不可搭配 {vae}；請使用 wan2.2_vae"
        )
    if is_14b and _VAE_WAN22.search(vae):
        raise ModelValidationError(
            f"VAE 不可混用：模型 {model_name}（Wan 14B）不可搭配 {vae}；請使用 wan_2.1_vae"
        )


def _resolve_model_path(raw: str, *, models_root: Path | None) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    if models_root is not None:
        return (models_root / path).resolve()
    return path.resolve()


def validate_required_models(
    session: Session,
    required: list[str],
    *,
    models_root: Path | str | None = None,
    check_sha256: bool = False,
) -> list[dict[str, Any]]:
    """執行前校驗：缺檔 → ModelValidationError（訊息含模型名）。"""
    if not required:
        return []
    root = Path(models_root) if models_root else _default_models_root()
    found: list[dict[str, Any]] = []
    for name in required:
        name = str(name).strip()
        if not name:
            continue
        row = session.scalar(select(ModelRegistry).where(ModelRegistry.name == name))
        if row is None:
            raise ModelValidationError(f"模型未註冊：{name}")
        _check_vae_compatibility(row.name, row.vae_name)
        path = _resolve_model_path(row.path, models_root=root)
        if not path.is_file():
            raise ModelValidationError(f"模型檔案不存在：{name}（path={path}）")
        if check_sha256 and row.sha256:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest.lower() != row.sha256.lower():
                raise ModelValidationError(
                    f"模型 sha256 不符：{name}（expected={row.sha256} actual={digest}）"
                )
        found.append(
            {
                "name": row.name,
                "path": str(path),
                "sha256": row.sha256,
                "vae_name": row.vae_name,
            }
        )
    return found


def _default_models_root() -> Path | None:
    raw = (os.getenv("LVS_MODELS_ROOT") or os.getenv("COMFYUI_MODELS_ROOT") or "").strip()
    return Path(raw) if raw else None
