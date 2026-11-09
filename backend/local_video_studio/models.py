"""M1 領域模型：Project / Script / Shot（SQLAlchemy 2）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
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
