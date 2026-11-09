"""領域模型：Project / Script / Shot / Job / Asset / Resource（SQLAlchemy 2）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


def _uuid() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "lvs_projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    scripts: Mapped[list["Script"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    shots: Mapped[list["Shot"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    jobs: Mapped[list["GenerationJob"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    assets: Mapped[list["Asset"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class Script(Base):
    __tablename__ = "lvs_scripts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("lvs_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    project: Mapped["Project"] = relationship(back_populates="scripts")


class Shot(Base):
    __tablename__ = "lvs_shots"
    __table_args__ = (UniqueConstraint("project_id", "scene_no", "shot_no", name="uq_lvs_shot"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("lvs_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scene_no: Mapped[int] = mapped_column(Integer, nullable=False)
    shot_no: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    dialogue: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_sec: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=5)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    selected_keyframe_asset_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    selected_clip_asset_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    project: Mapped["Project"] = relationship(back_populates="shots")


class GenerationJob(Base):
    __tablename__ = "lvs_generation_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("lvs_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    shot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("lvs_shots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_type: Mapped[str] = mapped_column(String(32), nullable=False)
    workflow_template: Mapped[str] = mapped_column(String(128), nullable=False)
    params_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    data_class: Mapped[str] = mapped_column(String(32), nullable=False, default="local_only")
    assigned_agent: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    project: Mapped["Project"] = relationship(back_populates="jobs")
    resources: Mapped[list["ResourceRecord"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class Asset(Base):
    __tablename__ = "lvs_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("lvs_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    shot_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("lvs_shots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    mime: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    project: Mapped["Project"] = relationship(back_populates="assets")


class ResourceRecord(Base):
    __tablename__ = "lvs_resource_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("lvs_generation_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    gpu_minutes: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    wall_minutes: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    attempts: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    discarded_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    storage_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    api_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    electricity_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    job: Mapped["GenerationJob"] = relationship(back_populates="resources")
