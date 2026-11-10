"""採集結果目錄 → UnifiedPost + 縮圖。"""

from __future__ import annotations

import hashlib
import json
import logging
import mimetypes
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.media_vault import db as vault_db
from backend.media_vault.config import MediaVaultConfig, load_config
from backend.media_vault.models import normalize_compliance, risk_level_from_compliance

logger = logging.getLogger(__name__)

_IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"})


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _dedup_hash(platform: str, source_url: str, rel_path: str) -> str:
    raw = f"{platform}|{source_url}|{rel_path}".encode()
    return hashlib.sha256(raw).hexdigest()


def _load_pillow():
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow 未安裝，無法生成縮圖") from exc
    return Image


def ingest_job_results(
    job_id: str,
    results_dir: Path | str,
    *,
    platform: str = "",
    batch_id: str | None = None,
    crawl_method: str = "",
    compliance_basis: str | None = None,
) -> dict[str, Any]:
    """掃描 MediaCrawler 任務結果目錄並寫入媒資庫（best-effort）。"""
    cfg = load_config()
    vault_db.ensure_media_dirs(cfg)
    root = Path(results_dir)
    if not root.is_dir():
        msg = f"results_dir 不存在: {root}"
        vault_db.log_ingest_event(job_id=job_id, batch_id=batch_id or job_id, message=msg)
        return {"ingested": 0, "skipped": 0, "errors": [msg]}

    plat = platform or "unknown"
    batch = batch_id or job_id
    basis = normalize_compliance(compliance_basis or "public")
    risk = risk_level_from_compliance(basis)
    stats: dict[str, Any] = {"ingested": 0, "skipped": 0, "errors": []}

    records = _collect_records(root, plat)
    image_files = _collect_loose_images(root)

    if not records and image_files:
        for img in image_files:
            records.append(
                {
                    "platform": plat,
                    "source_url": "",
                    "author": "",
                    "caption": img.name,
                    "image_paths": [img],
                }
            )

    for rec in records:
        try:
            n = _ingest_record(
                rec,
                cfg=cfg,
                job_id=job_id,
                batch_id=batch,
                crawl_method=crawl_method,
                compliance_basis=basis,
                risk_level=risk,
            )
            stats["ingested"] += n
        except Exception as exc:
            logger.warning("media_vault ingest record failed: %s", exc)
            stats["errors"].append(str(exc))
            vault_db.log_ingest_event(job_id=job_id, batch_id=batch, message=str(exc))

    if stats["errors"]:
        vault_db.log_ingest_event(
            job_id=job_id,
            batch_id=batch,
            level="warn",
            message=f"ingest finished with {len(stats['errors'])} error(s)",
        )
    return stats


def _collect_loose_images(root: Path) -> list[Path]:
    out: list[Path] = []
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in _IMAGE_SUFFIXES:
            out.append(path)
    return out


def _collect_records(root: Path, platform: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() == ".jsonl":
            records.extend(_parse_jsonl(path, platform, root))
        elif path.suffix.lower() == ".json" and path.name not in {"jobs.json"}:
            records.extend(_parse_json_file(path, platform, root))
    return records


def _parse_jsonl(path: Path, platform: str, root: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            rec = _normalize_record(obj, platform, root, path.parent)
            if rec:
                out.append(rec)
    return out


def _parse_json_file(path: Path, platform: str, root: Path) -> list[dict[str, Any]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items: list[Any]
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        for key in ("data", "notes", "items", "results"):
            if isinstance(raw.get(key), list):
                items = raw[key]
                break
        else:
            items = [raw]
    else:
        return []
    out: list[dict[str, Any]] = []
    for obj in items:
        if isinstance(obj, dict):
            rec = _normalize_record(obj, platform, root, path.parent)
            if rec:
                out.append(rec)
    return out


def _normalize_record(obj: dict[str, Any], platform: str, root: Path, base: Path) -> dict[str, Any] | None:
    plat = str(obj.get("platform") or platform or "unknown")
    source_url = str(
        obj.get("source_url")
        or obj.get("url")
        or obj.get("note_url")
        or obj.get("aweme_url")
        or ""
    )
    author = str(obj.get("author") or obj.get("user_name") or obj.get("nickname") or "")
    caption = str(obj.get("caption") or obj.get("title") or obj.get("desc") or obj.get("description") or "")
    image_paths = _resolve_image_list(obj, base, root)
    if not image_paths and not source_url and not caption:
        return None
    return {
        "platform": plat,
        "source_url": source_url,
        "author": author,
        "caption": caption,
        "image_paths": image_paths,
    }


def _resolve_image_list(obj: dict[str, Any], base: Path, root: Path) -> list[Path]:
    paths: list[Path] = []
    candidates: list[Any] = []
    for key in ("image_list", "images", "image_urls", "pics", "cover", "local_images"):
        val = obj.get(key)
        if val is None:
            continue
        if isinstance(val, str):
            candidates.append(val)
        elif isinstance(val, list):
            candidates.extend(val)

    for item in candidates:
        if isinstance(item, dict):
            ref = item.get("url") or item.get("path") or item.get("local_path")
        else:
            ref = str(item)
        if not ref or ref.startswith("http"):
            continue
        p = Path(ref)
        if not p.is_absolute():
            p = (base / ref).resolve()
        if p.is_file():
            paths.append(p)
        else:
            alt = (root / ref).resolve()
            if alt.is_file():
                paths.append(alt)
    return paths


def _ingest_record(
    rec: dict[str, Any],
    *,
    cfg: MediaVaultConfig,
    job_id: str,
    batch_id: str,
    crawl_method: str,
    compliance_basis: str,
    risk_level: str,
) -> int:
    platform = rec["platform"]
    source_url = rec.get("source_url") or ""
    image_paths: list[Path] = list(rec.get("image_paths") or [])
    if not image_paths:
        dedup = _dedup_hash(platform, source_url, rec.get("caption") or "")
        if vault_db.find_post_by_dedup(dedup):
            return 0
        vault_db.insert_post(
            {
                "platform": platform,
                "source_url": source_url,
                "author": rec.get("author") or "",
                "batch_id": batch_id,
                "job_id": job_id,
                "compliance_basis": compliance_basis,
                "crawl_method": crawl_method,
                "media_type": "text",
                "caption": rec.get("caption"),
                "dedup_hash": dedup,
                "risk_level": risk_level,
                "created_at": _utc_now(),
                "ingested_at": _utc_now(),
            }
        )
        return 1

    count = 0
    for img_path in image_paths:
        if img_path.suffix.lower() not in _IMAGE_SUFFIXES:
            continue
        rel_key = f"{batch_id}/{img_path.name}"
        dedup = _dedup_hash(platform, source_url, rel_key)
        if vault_db.find_post_by_dedup(dedup):
            continue
        post_id = vault_db.insert_post(
            {
                "platform": platform,
                "source_url": source_url,
                "author": rec.get("author") or "",
                "batch_id": batch_id,
                "job_id": job_id,
                "compliance_basis": compliance_basis,
                "crawl_method": crawl_method,
                "media_type": "image",
                "caption": rec.get("caption"),
                "dedup_hash": dedup,
                "risk_level": risk_level,
                "created_at": _utc_now(),
                "ingested_at": _utc_now(),
            }
        )
        _store_image_assets(cfg, post_id, img_path, batch_id)
        count += 1
    return count


def _store_image_assets(cfg: MediaVaultConfig, post_id: str, src: Path, batch_id: str) -> None:
    Image = _load_pillow()
    dest_name = f"{uuid.uuid4().hex}{src.suffix.lower()}"
    rel_original = f"originals/{batch_id}/{dest_name}"
    abs_original = cfg.media_root / rel_original
    abs_original.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, abs_original)
    mime = mimetypes.guess_type(src.name)[0] or "application/octet-stream"
    width: int | None = None
    height: int | None = None
    try:
        with Image.open(abs_original) as im:
            width, height = im.size
            for kind, max_side in (("thumb_300", 300), ("thumb_800", 800)):
                thumb = im.copy()
                thumb.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
                rel_thumb = f"thumbs/{post_id}_{kind}{src.suffix.lower()}"
                abs_thumb = cfg.media_root / rel_thumb
                abs_thumb.parent.mkdir(parents=True, exist_ok=True)
                thumb.save(abs_thumb, format=im.format or "JPEG")
                vault_db.insert_asset(
                    {
                        "post_id": post_id,
                        "kind": kind,
                        "relative_path": rel_thumb,
                        "byte_size": abs_thumb.stat().st_size,
                        "width": thumb.size[0],
                        "height": thumb.size[1],
                        "mime": mime,
                    }
                )
    except OSError as exc:
        vault_db.log_ingest_event(message=f"thumb failed for {src}: {exc}")

    vault_db.insert_asset(
        {
            "post_id": post_id,
            "kind": "original",
            "relative_path": rel_original,
            "byte_size": abs_original.stat().st_size,
            "width": width,
            "height": height,
            "mime": mime,
        }
    )
