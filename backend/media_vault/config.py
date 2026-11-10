"""Media Vault 執行期路徑與連線設定。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "backend" / "data" / "media_vault.sqlite3"
DEFAULT_MEDIA_ROOT = PROJECT_ROOT / "backend" / "data" / "media_vault_media"


@dataclass(frozen=True)
class MediaVaultConfig:
    database_path: Path
    media_root: Path

    @property
    def originals_dir(self) -> Path:
        return self.media_root / "originals"

    @property
    def thumbs_dir(self) -> Path:
        return self.media_root / "thumbs"


def load_config() -> MediaVaultConfig:
    db_url = os.environ.get("MEDIA_VAULT_DATABASE_URL", "").strip()
    if db_url.startswith("sqlite:///"):
        raw = db_url.removeprefix("sqlite:///")
        db_path = Path(raw) if raw != ":memory:" else Path(":memory:")
    elif db_url:
        db_path = Path(db_url)
    else:
        db_path = DEFAULT_DB_PATH

    media_root = Path(os.environ.get("MEDIA_VAULT_MEDIA_ROOT", str(DEFAULT_MEDIA_ROOT)))
    return MediaVaultConfig(database_path=db_path, media_root=media_root)
