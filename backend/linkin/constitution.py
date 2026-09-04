"""世界觀憲法：世界基石、三大陣營、靈絲術、內容邊界與一致性約束。"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

DEFAULT_CONSTITUTION_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "linkin_constitution.json"
)

_cache: dict[str, Any] | None = None


class ConstitutionError(ValueError):
    """憲法資料不合法。"""


def constitution_path() -> Path:
    override = os.getenv("EVOL_LINKIN_CONSTITUTION_PATH")
    if override:
        return Path(override)
    return DEFAULT_CONSTITUTION_PATH


def reset_cache() -> None:
    global _cache
    _cache = None


def _load_raw() -> dict[str, Any]:
    path = constitution_path()
    if not path.exists():
        fallback = DEFAULT_CONSTITUTION_PATH
        if fallback.exists() and fallback != path:
            data = json.loads(fallback.read_text(encoding="utf-8"))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return data
        raise ConstitutionError(f"找不到憲法檔：{path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ConstitutionError(f"憲法檔無法解析：{exc}") from exc
    if not isinstance(data, dict):
        raise ConstitutionError("憲法檔必須為 JSON 物件")
    return data


def load_constitution() -> dict[str, Any]:
    global _cache
    if _cache is None:
        _cache = _load_raw()
    return deepcopy(_cache)


def save_constitution(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ConstitutionError("憲法必須為 JSON 物件")
    if not str(data.get("world_name") or "").strip():
        raise ConstitutionError("憲法必須包含 world_name")
    path = constitution_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    global _cache
    _cache = deepcopy(data)
    return load_constitution()


def update_constitution(patch: dict[str, Any]) -> dict[str, Any]:
    current = load_constitution()
    merged = {**current, **patch}
    if "foundation" in patch and isinstance(current.get("foundation"), dict) and isinstance(patch["foundation"], dict):
        merged["foundation"] = {**current["foundation"], **patch["foundation"]}
    if "magic" in patch and isinstance(current.get("magic"), dict) and isinstance(patch["magic"], dict):
        merged["magic"] = {**current["magic"], **patch["magic"]}
        if "schools" in patch["magic"]:
            merged["magic"]["schools"] = patch["magic"]["schools"]
    return save_constitution(merged)


def region_style_map() -> dict[str, list[str]]:
    """區域名稱 → 允許的建築風格。"""
    const = load_constitution()
    mapping: dict[str, list[str]] = {}
    for region in const.get("regions") or []:
        name = str(region.get("name") or "").strip()
        styles = [str(s).strip() for s in (region.get("allowed_styles") or []) if str(s).strip()]
        if name and styles:
            mapping[name] = styles
    for faction in const.get("factions") or []:
        name = str(faction.get("name") or "").strip()
        capital = str(faction.get("capital") or "").strip()
        styles = [str(s).strip() for s in (faction.get("allowed_styles") or []) if str(s).strip()]
        if name and styles:
            mapping.setdefault(name, styles)
        if capital and styles:
            mapping.setdefault(capital, styles)
    return mapping


def allowed_styles_for_region(region: str | None) -> list[str] | None:
    """未知區域回傳 None（不強制風格）；已知區域回傳允許清單。"""
    if not region or not str(region).strip():
        return None
    key = str(region).strip()
    mapping = region_style_map()
    if key in mapping:
        return mapping[key]
    for name, styles in mapping.items():
        if key in name or name in key:
            return styles
    return None


def max_blocks_per_call() -> int:
    const = load_constitution()
    builder = const.get("builder") or {}
    try:
        return int(builder.get("max_blocks_per_call") or 5000)
    except (TypeError, ValueError):
        return 5000


def item_balance() -> dict[str, Any]:
    const = load_constitution()
    return dict(const.get("item_balance") or {})


def worldview_seed_documents() -> list[dict[str, Any]]:
    """將憲法拆成 RAG 種子文件。"""
    const = load_constitution()
    docs: list[dict[str, Any]] = []
    foundation = const.get("foundation") or {}
    docs.append(
        {
            "id": "world-foundation",
            "text": (
                f"世界名称：{foundation.get('name') or const.get('world_name')}\n"
                f"起源：{foundation.get('origin')}\n"
                f"核心冲突：{foundation.get('core_conflict')}\n"
                f"造物主：{foundation.get('creator')}\n"
                f"核心意志：{foundation.get('will')}"
            ),
            "metadata": {"kind": "foundation", "collection_hint": "worldview"},
        }
    )
    magic = const.get("magic") or {}
    schools = "、".join(
        f"{s.get('name')}（{s.get('domain')}）" for s in (magic.get("schools") or [])
    )
    docs.append(
        {
            "id": "world-magic",
            "text": (
                f"魔法体系：{magic.get('name')}（{magic.get('alias')}）\n"
                f"来源：{magic.get('source')}\n"
                f"原则：{magic.get('principle')}\n"
                f"学派：{schools}\n"
                f"限制：{'；'.join(magic.get('limits') or [])}"
            ),
            "metadata": {"kind": "magic", "collection_hint": "worldview"},
        }
    )
    for faction in const.get("factions") or []:
        fid = str(faction.get("id") or faction.get("name"))
        docs.append(
            {
                "id": f"faction-{fid}",
                "text": (
                    f"阵营：{faction.get('name')}（{faction.get('alias')}）\n"
                    f"倾向：{faction.get('alignment')}\n"
                    f"都城：{faction.get('capital')}\n"
                    f"信条：{faction.get('creed')}\n"
                    f"美学：{faction.get('aesthetic')}\n"
                    f"张力：{faction.get('tension')}"
                ),
                "metadata": {
                    "kind": "faction",
                    "faction_id": fid,
                    "region": faction.get("capital") or "",
                },
            }
        )
    for region in const.get("regions") or []:
        rid = str(region.get("id") or region.get("name"))
        styles = "、".join(region.get("allowed_styles") or [])
        docs.append(
            {
                "id": f"region-{rid}",
                "text": (
                    f"区域：{region.get('name')}\n"
                    f"文化：{region.get('culture')}\n"
                    f"允许建筑风格：{styles}"
                ),
                "metadata": {
                    "kind": "region",
                    "region": region.get("name") or "",
                    "faction_id": region.get("faction_id") or "",
                },
            }
        )
    docs.append(
        {
            "id": "world-boundaries",
            "text": "内容边界：\n- " + "\n- ".join(const.get("content_boundaries") or []),
            "metadata": {"kind": "boundary"},
        }
    )
    docs.append(
        {
            "id": "world-consistency",
            "text": "一致性约束：\n- " + "\n- ".join(const.get("consistency_rules") or []),
            "metadata": {"kind": "consistency"},
        }
    )
    return docs
