"""MediaCrawler 結果目錄路徑牢籠。"""

from __future__ import annotations

from pathlib import Path

from backend.mediacrawler.config import (
    MediaCrawlerConfigError,
    MediaCrawlerEnvConfig,
    load_env_config,
)


def resolve_results_root(env: MediaCrawlerEnvConfig | None = None) -> Path:
    cfg = env or load_env_config()
    root = cfg.results_root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def job_results_dir(job_id: str, env: MediaCrawlerEnvConfig | None = None) -> Path:
    safe_id = _safe_job_id(job_id)
    root = resolve_results_root(env)
    path = (root / safe_id).resolve()
    _assert_under_root(path, root)
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_result_path(job_id: str, filename: str, env: MediaCrawlerEnvConfig | None = None) -> Path:
    safe_id = _safe_job_id(job_id)
    name = _safe_filename(filename)
    root = resolve_results_root(env)
    path = (root / safe_id / name).resolve()
    _assert_under_root(path, root)
    return path


def list_result_files(job_id: str, env: MediaCrawlerEnvConfig | None = None) -> list[dict[str, str | int]]:
    directory = job_results_dir(job_id, env)
    items: list[dict[str, str | int]] = []
    if not directory.is_dir():
        return items
    for entry in sorted(directory.iterdir()):
        if not entry.is_file():
            continue
        if entry.name.startswith("."):
            continue
        try:
            size = entry.stat().st_size
        except OSError:
            size = 0
        items.append({"name": entry.name, "size": size, "path": str(entry)})
    return items


def _safe_job_id(job_id: str) -> str:
    value = (job_id or "").strip()
    if not value or "/" in value or "\\" in value or ".." in value:
        raise MediaCrawlerConfigError("非法 job_id", code="path")
    if not all(c.isalnum() or c in "-_" for c in value):
        raise MediaCrawlerConfigError("非法 job_id 字元", code="path")
    return value


def _safe_filename(filename: str) -> str:
    name = Path((filename or "").strip()).name
    if not name or name in {".", ".."}:
        raise MediaCrawlerConfigError("非法檔名", code="path")
    if ".." in name or "/" in name or "\\" in name:
        raise MediaCrawlerConfigError("非法檔名", code="path")
    return name


def _assert_under_root(path: Path, root: Path) -> None:
    try:
        path.relative_to(root)
    except ValueError:
        raise MediaCrawlerConfigError("路徑越界", code="path") from None
