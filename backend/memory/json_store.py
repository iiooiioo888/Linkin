"""Phase 1 暫定記憶儲存：JSON 檔案（Task 1.4）。

Phase 2 將以 ChromaDB 向量資料庫取代（介面保持一致：
add_memory / 查詢 / reset），讓節點層不需改動。
"""

import json
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_STORE_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "memory_store.json"
)


class JsonMemoryStore:
    """以 JSON 檔案儲存的簡易記憶庫。

    未指定路徑時：已登入帳號寫入自己的 ``memory_store.json``，
    否則用 ``EVOL_MEMORY_STORE_PATH`` 或預設檔。
    """

    def __init__(self, path: str | Path | None = None):
        self._path_arg = Path(path) if path else None

    @property
    def path(self) -> Path:
        if self._path_arg is not None:
            return self._path_arg
        import os

        from backend.core.user_settings import active_settings_user, user_settings_dir

        uid = active_settings_user()
        if uid:
            return user_settings_dir(uid) / "memory_store.json"
        override = os.getenv("EVOL_MEMORY_STORE_PATH", "").strip()
        if override:
            return Path(override)
        return DEFAULT_STORE_PATH

    def add_memory(self, text: str, metadata: dict | None = None) -> None:
        """新增一筆記憶（文字 + 後設資料）。"""
        memories = self._load()
        memories.append(
            {
                "text": text,
                "metadata": metadata or {},
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        self._save(memories)

    def all(self) -> list[dict]:
        """回傳全部記憶。"""
        return self._load()

    def reset(self) -> None:
        """清空記憶庫。"""
        self._save([])

    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []

    def _save(self, memories: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(memories, ensure_ascii=False, indent=2), encoding="utf-8"
        )