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
