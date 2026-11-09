"""Pydantic v2 schemas（M1）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None


class ProjectPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[str] = None


class ProjectOut(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    status: str
    created_at: datetime
    shot_count: int = 0

    model_config = {"from_attributes": True}


class ShotCreate(BaseModel):
    scene_no: int = Field(ge=0)
    shot_no: int = Field(ge=0)
    description: str = Field(min_length=1)
    dialogue: Optional[str] = None
    duration_sec: float = Field(default=5, gt=0, le=9999)


class ShotPatch(BaseModel):
    description: Optional[str] = Field(default=None, min_length=1)
    dialogue: Optional[str] = None
    duration_sec: Optional[float] = Field(default=None, gt=0, le=9999)
    status: Optional[str] = None
    selected_keyframe_asset_id: Optional[str] = None
    selected_clip_asset_id: Optional[str] = None


class ShotOut(BaseModel):
    id: str
    project_id: str
    scene_no: int
    shot_no: int
    description: str
    dialogue: Optional[str] = None
    duration_sec: float
    status: str
    selected_keyframe_asset_id: Optional[str] = None
    selected_clip_asset_id: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ScriptUpload(BaseModel):
    content_json: dict[str, Any]


class ScriptOut(BaseModel):
    id: str
    project_id: str
    content_json: dict[str, Any]
    version: int
    created_at: datetime
    imported_shots: int = 0

    model_config = {"from_attributes": True}


class JobCreate(BaseModel):
    project_id: str
    shot_id: str
    job_type: str = Field(pattern="^(keyframe|draft|refine|audio|compose)$")
    workflow_template: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)
    priority: int = 100
    data_class: str = "local_only"
    max_attempts: int = Field(default=3, ge=1, le=20)


class AssetPayload(BaseModel):
    relative_path: str
    type: str
    bytes: int | None = None
    sha256: str | None = None
    mime: str | None = None


class ResourcePayload(BaseModel):
    gpu_minutes: float | None = None
    wall_minutes: float | None = None
    attempts: int | None = None
    discarded_count: int = 0
    storage_bytes: int | None = None
    api_calls: int = 0
    electricity_note: str | None = None


class JobComplete(BaseModel):
    status: str = Field(pattern="^(succeeded|failed)$")
    error: str | None = None
    asset: AssetPayload | None = None
    resource: ResourcePayload | None = None


class AssetOut(BaseModel):
    id: str
    project_id: str
    shot_id: str | None = None
    type: str
    relative_path: str
    mime: str | None = None
    bytes: int | None = None
    sha256: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class JobOut(BaseModel):
    id: str
    project_id: str
    shot_id: str
    job_type: str
    workflow_template: str
    params_json: dict[str, Any]
    status: str
    attempt: int
    max_attempts: int
    priority: int
    data_class: str
    assigned_agent: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    created_at: datetime
    asset: AssetOut | None = None

    model_config = {"from_attributes": True}
