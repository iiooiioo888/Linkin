"""SQLAlchemy engine／session（預設 SQLite；可切 PostgreSQL）。"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.local_video_studio.config import load_config
from backend.local_video_studio.models import Base

_lock = threading.RLock()
_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _default_sqlite_url() -> str:
    root = Path(__file__).resolve().parents[1] / "data"
    root.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{root / 'local_video_studio.sqlite3'}"


def _normalize_url(raw: str) -> str:
    url = (raw or "").strip()
    if not url:
        return _default_sqlite_url()
    # 允許檔案路徑寫法：sqlite:////abs 或純路徑
    if url.startswith("sqlite:///"):
        return url
    if url.endswith(".sqlite3") or url.endswith(".db"):
        path = Path(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{path}"
    return url


def _enable_sqlite_fk(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return

    @event.listens_for(engine, "connect")
    def _set_fk(dbapi_conn, _connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_engine() -> Engine:
    global _engine, _SessionLocal
    with _lock:
        if _engine is None:
            cfg = load_config()
            url = _normalize_url(cfg.database_url)
            kwargs: dict = {"future": True}
            if url.startswith("sqlite:"):
                kwargs["connect_args"] = {"check_same_thread": False}
            _engine = create_engine(url, **kwargs)
            _enable_sqlite_fk(_engine)
            _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
        return _engine


def get_session_factory() -> sessionmaker[Session]:
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal


def init_db() -> None:
    """建立 M1 表（SQLite create_all；等同 Alembic 初始遷移效果）。"""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS lvs_schema_meta ("
                "key VARCHAR(64) PRIMARY KEY, value VARCHAR(64) NOT NULL)"
            )
        )
        existing = conn.execute(
            text("SELECT value FROM lvs_schema_meta WHERE key = 'revision'")
        ).fetchone()
        if existing is None:
            conn.execute(
                text("INSERT INTO lvs_schema_meta(key, value) VALUES ('revision', 'm1_001')")
            )


@contextmanager
def session_scope() -> Iterator[Session]:
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_db_state() -> None:
    """測試用：關閉 engine，下次重新綁定。"""
    global _engine, _SessionLocal
    with _lock:
        if _engine is not None:
            _engine.dispose()
        _engine = None
        _SessionLocal = None
