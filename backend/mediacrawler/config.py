"""MediaCrawler 環境與運行時配置。"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_TRUE = {"1", "true", "yes", "on", "y"}

PLATFORMS = frozenset({"xhs", "dy", "ks", "bili", "wb", "tieba", "zhihu"})
CRAWL_TYPES = frozenset({"search", "detail", "creator"})
LOGIN_TYPES = frozenset({"cookie", "qrcode"})
SAVE_FORMATS = frozenset({"json", "csv", "jsonl", "xlsx", "sqlite", "db"})

DEFAULT_RESULTS_ROOT = Path("backend/data/mediacrawler/results")
DEFAULT_RUNTIME_CONFIG = Path("backend/data/mediacrawler/runtime.json")
DEFAULT_JOBS_STORE = Path("backend/data/mediacrawler/jobs.json")

_PLATFORM_ALIASES = {
    "xiaohongshu": "xhs",
    "douyin": "dy",
    "kuaishou": "ks",
    "bilibili": "bili",
    "weibo": "wb",
}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in _TRUE


def normalize_platform(value: str) -> str:
    v = (value or "").strip().lower()
    return _PLATFORM_ALIASES.get(v, v)


@dataclass
class MediaCrawlerEnvConfig:
    enabled: bool = False
    home: Path | None = None
    results_root: Path = field(default_factory=lambda: DEFAULT_RESULTS_ROOT)
    runtime_config_path: Path = field(default_factory=lambda: DEFAULT_RUNTIME_CONFIG)
    jobs_store_path: Path = field(default_factory=lambda: DEFAULT_JOBS_STORE)
    max_concurrent_jobs: int = 2
    job_timeout_seconds: int = 3600

    @property
    def dry_run(self) -> bool:
        return not self.enabled


def load_env_config() -> MediaCrawlerEnvConfig:
    home_raw = os.getenv("MEDIACRAWLER_HOME", "").strip()
    home = Path(home_raw).expanduser() if home_raw else None
    results_raw = os.getenv("EVOL_MEDIACRAWLER_RESULTS_ROOT", "").strip()
    results_root = Path(results_raw).expanduser() if results_raw else DEFAULT_RESULTS_ROOT
    runtime_raw = os.getenv("EVOL_MEDIACRAWLER_CONFIG", "").strip()
    runtime_config_path = Path(runtime_raw).expanduser() if runtime_raw else DEFAULT_RUNTIME_CONFIG
    jobs_raw = os.getenv("EVOL_MEDIACRAWLER_JOBS_STORE", "").strip()
    jobs_store_path = Path(jobs_raw).expanduser() if jobs_raw else DEFAULT_JOBS_STORE
    max_jobs = max(1, min(4, int(os.getenv("EVOL_MEDIACRAWLER_MAX_JOBS", "2") or "2")))
    timeout = max(60, min(24 * 3600, int(os.getenv("EVOL_MEDIACRAWLER_TIMEOUT", "3600") or "3600")))
    return MediaCrawlerEnvConfig(
        enabled=_env_bool("EVOL_MEDIACRAWLER_ENABLED", False),
        home=home,
        results_root=results_root,
        runtime_config_path=runtime_config_path,
        jobs_store_path=jobs_store_path,
        max_concurrent_jobs=max_jobs,
        job_timeout_seconds=timeout,
    )


@dataclass
class CrawlJobRequest:
    platform: str
    crawl_type: str
    login_type: str = "cookie"
    keywords: str = ""
    post_ids: str = ""
    creator_ids: str = ""
    enable_comments: bool = False
    save_format: str = "json"
    max_notes: int = 20
    dry_run: bool = False
    cookie: str = ""

    def normalized(self) -> CrawlJobRequest:
        return CrawlJobRequest(
            platform=normalize_platform(self.platform),
            crawl_type=(self.crawl_type or "search").strip().lower(),
            login_type=(self.login_type or "cookie").strip().lower(),
            keywords=(self.keywords or "").strip(),
            post_ids=(self.post_ids or "").strip(),
            creator_ids=(self.creator_ids or "").strip(),
            enable_comments=bool(self.enable_comments),
            save_format=(self.save_format or "json").strip().lower(),
            max_notes=max(1, min(500, int(self.max_notes or 20))),
            dry_run=bool(self.dry_run),
            cookie=(self.cookie or "").strip(),
        )


class MediaCrawlerConfigError(ValueError):
    def __init__(self, message: str, *, code: str = "invalid"):
        super().__init__(message)
        self.code = code


def _read_runtime_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _write_runtime_config(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def get_stored_cookie(env: MediaCrawlerEnvConfig | None = None) -> str:
    cfg = env or load_env_config()
    data = _read_runtime_config(cfg.runtime_config_path)
    return str(data.get("cookie") or "").strip()


def set_stored_cookie(cookie: str, env: MediaCrawlerEnvConfig | None = None) -> None:
    cfg = env or load_env_config()
    data = _read_runtime_config(cfg.runtime_config_path)
    data["cookie"] = (cookie or "").strip()
    _write_runtime_config(cfg.runtime_config_path, data)


def mask_secret(value: str, visible: int = 4) -> str:
    v = (value or "").strip()
    if not v:
        return ""
    if len(v) <= visible * 2:
        return "*" * len(v)
    return f"{v[:visible]}…{v[-visible:]}"


def detect_installation(home: Path | None) -> dict[str, Any]:
    if home is None:
        return {"installed": False, "reason": "MEDIACRAWLER_HOME 未設定"}
    if not home.is_dir():
        return {"installed": False, "reason": f"目錄不存在：{home}"}
    main_py = home / "main.py"
    if not main_py.is_file():
        return {"installed": False, "reason": f"缺少 main.py：{main_py}"}
    has_uv = (home / "uv.lock").is_file() or (home / "pyproject.toml").is_file()
    return {
        "installed": True,
        "home": str(home),
        "main_py": str(main_py),
        "runner": "uv" if has_uv else "python",
    }


def validate_job_request(req: CrawlJobRequest, env: MediaCrawlerEnvConfig | None = None) -> list[str]:
    """回傳錯誤列表；空列表表示通過。"""
    cfg = env or load_env_config()
    errors: list[str] = []
    r = req.normalized()

    if r.platform not in PLATFORMS:
        errors.append(f"不支援的平台：{r.platform}")
    if r.crawl_type not in CRAWL_TYPES:
        errors.append(f"不支援的採集類型：{r.crawl_type}")
    if r.login_type not in LOGIN_TYPES:
        errors.append(f"不支援的登入方式：{r.login_type}")
    if r.save_format not in SAVE_FORMATS:
        errors.append(f"不支援的輸出格式：{r.save_format}")

    if r.crawl_type == "search" and not r.keywords:
        errors.append("搜尋模式需提供 keywords")
    if r.crawl_type == "detail" and not r.post_ids:
        errors.append("詳情模式需提供 post_ids（逗號分隔）")
    if r.crawl_type == "creator" and not r.creator_ids:
        errors.append("創作者模式需提供 creator_ids（逗號分隔）")

    if r.login_type == "qrcode" and not r.dry_run:
        errors.append("QR 登入需在伺服器手動執行 MediaCrawler CLI；API v1 僅支援 cookie 或乾跑校驗")

    cookie = r.cookie or get_stored_cookie(cfg)
    if r.login_type == "cookie" and not cookie and not r.dry_run:
        errors.append("Cookie 登入需配置 cookie（UI 或 runtime.json）")

    install = detect_installation(cfg.home)
    if not install.get("installed"):
        errors.append(str(install.get("reason") or "MediaCrawler 未安裝"))

    if not r.dry_run and cfg.dry_run:
        errors.append("EVOL_MEDIACRAWLER_ENABLED 未啟用，僅可乾跑校驗")

    if r.keywords and len(r.keywords) > 500:
        errors.append("keywords 過長（上限 500 字）")
    for field_name, raw in (("post_ids", r.post_ids), ("creator_ids", r.creator_ids)):
        if raw and not re.fullmatch(r"[A-Za-z0-9_,\-\s]+", raw):
            errors.append(f"{field_name} 含非法字元")

    return errors


def integration_status(env: MediaCrawlerEnvConfig | None = None) -> dict[str, Any]:
    cfg = env or load_env_config()
    install = detect_installation(cfg.home)
    cookie = get_stored_cookie(cfg)
    tier = "needsKey"
    if install.get("installed") and cookie:
        tier = "available" if cfg.dry_run else "enabled"
    elif install.get("installed"):
        tier = "available"
    return {
        "enabled": cfg.enabled,
        "dry_run": cfg.dry_run,
        "tier": tier,
        "installation": install,
        "results_root": str(cfg.results_root),
        "max_concurrent_jobs": cfg.max_concurrent_jobs,
        "cookie_configured": bool(cookie),
        "cookie_preview": mask_secret(cookie) if cookie else "",
        "platforms": sorted(PLATFORMS),
        "crawl_types": sorted(CRAWL_TYPES),
        "login_types": ["cookie", "qrcode"],
        "legal_notice": (
            "僅供學習與研究；請遵守各平台服務條款與 robots 規則，"
            "僅採集公開資料，使用者自行承擔法律責任。"
        ),
    }
