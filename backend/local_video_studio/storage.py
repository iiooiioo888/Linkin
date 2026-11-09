"""LocalPathStorage：相對路徑僅允許落在 STORAGE_BASE 下。"""

from __future__ import annotations

import shutil
from pathlib import Path

from backend.local_video_studio.config import load_config

_PROJECT_SUBDIRS = (
    "script",
    "keyframes",
    "drafts",
    "refines",
    "audio",
    "output",
    "logs",
    "resources",
)


class StorageError(ValueError):
    pass


class LocalPathStorage:
    def __init__(self, base: str | Path | None = None):
        cfg = load_config()
        self.base = Path(base or cfg.storage_base).resolve()

    def resolve(self, relative_path: str) -> Path:
        rel = (relative_path or "").lstrip("/").replace("\\", "/")
        if not rel or ".." in Path(rel).parts:
            raise StorageError("非法相對路徑")
        full = (self.base / rel).resolve()
        if self.base != full and self.base not in full.parents:
            raise StorageError("路徑逃逸 STORAGE_BASE")
        return full

    def ensure_project_dirs(self, project_id: str) -> Path:
        root = self.resolve(f"projects/{project_id}")
        root.mkdir(parents=True, exist_ok=True)
        for name in _PROJECT_SUBDIRS:
            (root / name).mkdir(parents=True, exist_ok=True)
        return root

    def stat(self, relative_path: str) -> dict:
        path = self.resolve(relative_path)
        if not path.exists():
            return {"exists": False, "relative_path": relative_path}
        st = path.stat()
        return {
            "exists": True,
            "relative_path": relative_path,
            "bytes": st.st_size,
            "is_file": path.is_file(),
            "is_dir": path.is_dir(),
        }

    def delete(self, relative_path: str) -> None:
        path = self.resolve(relative_path)
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()

    def write_bytes(self, relative_path: str, data: bytes) -> Path:
        path = self.resolve(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path


def get_storage() -> LocalPathStorage:
    return LocalPathStorage()
