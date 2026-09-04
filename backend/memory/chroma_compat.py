"""ChromaDB 本機相容：防毒常攔截 .sql，改讀同名 .sql.txt 遷移檔。"""

from __future__ import annotations

from typing import Any


def apply_chromadb_sql_txt_compat() -> None:
    """讓 find_migrations 同時接受 *.sql 與 *.sql.txt。"""
    from chromadb.db import migrations

    existing = migrations.find_migrations
    if getattr(existing, "_linkin_sql_txt", False):
        return

    def find_migrations(dir: Any, scope: str, hash_alg: str = "md5"):
        files = []
        for item in dir.iterdir():
            name = item.name
            if name.endswith(".sql.txt"):
                name = name[:-4]
            elif not name.endswith(".sql"):
                continue
            files.append(migrations._parse_migration_filename(dir.name, name, item))
        files = [item for item in files if item["scope"] == scope]
        files = sorted(files, key=lambda item: item["version"])
        return [migrations._read_migration_file(item, hash_alg) for item in files]

    find_migrations._linkin_sql_txt = True  # type: ignore[attr-defined]
    migrations.find_migrations = find_migrations
