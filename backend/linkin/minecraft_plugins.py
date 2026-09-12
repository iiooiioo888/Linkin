"""Minecraft 第三方插件目錄、設定持久化與地圖 URL 探測。"""

from __future__ import annotations

import ipaddress
import json
import logging
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from backend.linkin.knowledge import COL_EVENTS, data_dir, get_store

logger = logging.getLogger(__name__)

SETTINGS_FILE = "minecraft_plugin_settings.json"

PLUGIN_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "id": "dynmap",
        "name": "Dynmap",
        "category": "map",
        "purpose": "經典 2D/3D 網頁地圖，支援多世界與標記層。",
        "platforms": ("Spigot", "Paper", "Fabric"),
        "install_hint": "下載 Dynmap.jar 至 plugins/，啟動後於 plugins/dynmap/configuration.txt 設定 webserver-port。",
        "config_fields": (
            {"key": "map_url", "label": "公開地圖 URL", "required": True, "example": "https://map.example.com/"},
            {"key": "api_port", "label": "Web 埠（可選）", "required": False, "example": "8123"},
        ),
        "embeddable": True,
        "related_flows": ("server-map",),
    },
    {
        "id": "bluemap",
        "name": "BlueMap",
        "category": "map",
        "purpose": "高品質 3D 網頁地圖，支援 Paper/Fabric/Forge。",
        "platforms": ("Paper", "Fabric", "Forge"),
        "install_hint": "安裝 BlueMap 插件／模組，於 config/bluemap/webserver.conf 啟用 web 伺服器。",
        "config_fields": (
            {"key": "map_url", "label": "公開地圖 URL", "required": True, "example": "https://map.example.com/"},
            {"key": "api_port", "label": "Web 埠（可選）", "required": False, "example": "8100"},
        ),
        "embeddable": True,
        "related_flows": ("server-map",),
    },
    {
        "id": "squaremap",
        "name": "Squaremap",
        "category": "map",
        "purpose": "Dynmap 的現代替代品，輕量 Paper 網頁地圖。",
        "platforms": ("Paper"),
        "install_hint": "安裝 squaremap.jar，於 plugins/squaremap/config.yml 設定 web-address 與 web-port。",
        "config_fields": (
            {"key": "map_url", "label": "公開地圖 URL", "required": True, "example": "https://map.example.com/"},
            {"key": "api_port", "label": "Web 埠（可選）", "required": False, "example": "8080"},
        ),
        "embeddable": True,
        "related_flows": ("server-map",),
    },
    {
        "id": "citizens",
        "name": "Citizens",
        "category": "npc",
        "purpose": "Spigot/Paper NPC 插件，與 Linkin NPC 工作流對照。",
        "platforms": ("Spigot", "Paper"),
        "install_hint": "安裝 Citizens.jar；NPC 資料存於 plugins/Citizens/saves.yml。",
        "config_fields": (
            {"key": "map_url", "label": "相關地圖 URL（可選）", "required": False},
        ),
        "embeddable": False,
        "related_flows": ("npcs",),
    },
    {
        "id": "fancynpcs",
        "name": "FancyNpcs",
        "category": "npc",
        "purpose": "現代 Paper NPC 插件，支援外觀與互動指令。",
        "platforms": ("Paper"),
        "install_hint": "安裝 FancyNpcs.jar 至 plugins/。",
        "config_fields": (),
        "embeddable": False,
        "related_flows": ("npcs",),
    },
    {
        "id": "quests",
        "name": "Quests",
        "category": "quest",
        "purpose": "Bukkit 任務插件，可與 Linkin 任務面板對照設計。",
        "platforms": ("Spigot", "Paper"),
        "install_hint": "安裝 Quests.jar；任務定義於 plugins/Quests/quests/。",
        "config_fields": (),
        "embeddable": False,
        "related_flows": ("quests",),
    },
    {
        "id": "worldedit",
        "name": "WorldEdit",
        "category": "build",
        "purpose": "區域選取與地形編輯；Linkin 建築派發為輕量標記，大量塑形需分批 fill。",
        "platforms": ("Spigot", "Paper", "Fabric"),
        "install_hint": "安裝 WorldEdit 或 FastAsyncWorldEdit；/.schem 可經 Linkin 建築面板匯入。",
        "config_fields": (),
        "embeddable": False,
        "related_flows": ("building",),
    },
)

_BLOCKED_HOSTS = frozenset(
    {
        "localhost",
        "metadata.google.internal",
        "metadata.google",
    }
)

_METADATA_IPS = frozenset({"169.254.169.254", "fd00:ec2::254"})


class PluginUrlError(ValueError):
    """URL 校驗或探測失敗。"""

    def __init__(self, message: str, code: str = "invalid_url"):
        super().__init__(message)
        self.code = code


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def settings_path() -> Path:
    return data_dir() / SETTINGS_FILE


def _default_settings() -> dict[str, Any]:
    return {
        "version": 1,
        "updated_at": _now(),
        "active_map_plugin": None,
        "plugins": {},
    }


def load_settings() -> dict[str, Any]:
    path = settings_path()
    if not path.is_file():
        return _default_settings()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("無法讀取 Minecraft 插件設定：%s", exc)
        return _default_settings()
    if not isinstance(raw, dict):
        return _default_settings()
    raw.setdefault("plugins", {})
    raw.setdefault("version", 1)
    return raw


def save_settings(settings: dict[str, Any]) -> dict[str, Any]:
    settings = {**settings, "updated_at": _now()}
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    return settings


def catalog_entry(plugin_id: str) -> dict[str, Any] | None:
    for item in PLUGIN_CATALOG:
        if item["id"] == plugin_id:
            return dict(item)
    return None


def list_catalog() -> list[dict[str, Any]]:
    settings = load_settings()
    plugins = settings.get("plugins") or {}
    active_map = settings.get("active_map_plugin")
    out: list[dict[str, Any]] = []
    for item in PLUGIN_CATALOG:
        stored = plugins.get(item["id"]) or {}
        map_url = str(stored.get("map_url") or "").strip()
        enabled = bool(stored.get("enabled"))
        status = _connection_status(item, stored)
        out.append(
            {
                **item,
                "enabled": enabled,
                "map_url": map_url or None,
                "api_port": stored.get("api_port"),
                "active_map": item["id"] == active_map,
                "status": status,
                "last_probe": stored.get("last_probe"),
            }
        )
    return out


def _connection_status(catalog: dict[str, Any], stored: dict[str, Any]) -> str:
    if not stored.get("enabled"):
        return "disabled"
    map_url = str(stored.get("map_url") or "").strip()
    if catalog.get("category") == "map" and not map_url:
        return "unconfigured"
    probe = stored.get("last_probe") or {}
    if probe.get("ok"):
        return "reachable"
    if probe.get("checked_at"):
        return "unreachable"
    if map_url and catalog.get("embeddable"):
        return "configured"
    if stored.get("enabled"):
        return "configured"
    return "unconfigured"


def get_plugin_settings(plugin_id: str) -> dict[str, Any] | None:
    entry = catalog_entry(plugin_id)
    if not entry:
        return None
    settings = load_settings()
    stored = dict((settings.get("plugins") or {}).get(plugin_id) or {})
    return {
        "id": plugin_id,
        "enabled": bool(stored.get("enabled")),
        "map_url": str(stored.get("map_url") or "").strip() or None,
        "api_port": stored.get("api_port"),
        "active_map": settings.get("active_map_plugin") == plugin_id,
        "last_probe": stored.get("last_probe"),
        "catalog": entry,
    }


def update_settings(body: dict[str, Any]) -> dict[str, Any]:
    settings = load_settings()
    plugins = dict(settings.get("plugins") or {})
    active_map = settings.get("active_map_plugin")

    if "active_map_plugin" in body:
        candidate = body.get("active_map_plugin")
        if candidate is not None:
            candidate = str(candidate).strip() or None
            if candidate and not catalog_entry(candidate):
                raise PluginUrlError(f"未知插件：{candidate}", code="unknown_plugin")
            active_map = candidate

    if "plugins" in body and isinstance(body["plugins"], dict):
        for plugin_id, patch in body["plugins"].items():
            if not catalog_entry(plugin_id):
                raise PluginUrlError(f"未知插件：{plugin_id}", code="unknown_plugin")
            if not isinstance(patch, dict):
                continue
            current = dict(plugins.get(plugin_id) or {})
            if "enabled" in patch:
                current["enabled"] = bool(patch["enabled"])
            if "map_url" in patch:
                url = str(patch.get("map_url") or "").strip()
                if url:
                    validate_map_url(url)
                current["map_url"] = url
            if "api_port" in patch:
                port = patch.get("api_port")
                current["api_port"] = int(port) if port not in (None, "") else None
            plugins[plugin_id] = current

    settings["plugins"] = plugins
    settings["active_map_plugin"] = active_map
    saved = save_settings(settings)
    _append_observability_event(
        "Minecraft 插件設定已更新",
        {"kind": "minecraft_plugin", "action": "settings_update", "active_map_plugin": active_map},
    )
    return public_settings(saved)


def public_settings(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = settings or load_settings()
    plugins = settings.get("plugins") or {}
    sanitized: dict[str, Any] = {}
    for plugin_id, stored in plugins.items():
        if not catalog_entry(plugin_id):
            continue
        sanitized[plugin_id] = {
            "enabled": bool(stored.get("enabled")),
            "map_url": str(stored.get("map_url") or "").strip() or None,
            "api_port": stored.get("api_port"),
            "last_probe": stored.get("last_probe"),
        }
    active = settings.get("active_map_plugin")
    map_url = _resolve_map_url(settings)
    return {
        "version": settings.get("version", 1),
        "updated_at": settings.get("updated_at"),
        "active_map_plugin": active,
        "map_url": map_url,
        "plugins": sanitized,
        "catalog_count": len(PLUGIN_CATALOG),
    }


def _resolve_map_url(settings: dict[str, Any]) -> str | None:
    plugins = settings.get("plugins") or {}
    active = settings.get("active_map_plugin")
    if active:
        url = str((plugins.get(active) or {}).get("map_url") or "").strip()
        if url:
            return url
    for plugin_id, stored in plugins.items():
        entry = catalog_entry(plugin_id)
        if not entry or entry.get("category") != "map":
            continue
        if stored.get("enabled"):
            url = str(stored.get("map_url") or "").strip()
            if url:
                return url
    return None


def validate_map_url(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        raise PluginUrlError("地圖 URL 不可為空", code="empty_url")
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "").lower()
    if scheme not in {"http", "https"}:
        raise PluginUrlError("僅允許 http 或 https URL", code="invalid_scheme")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise PluginUrlError("URL 缺少主機名", code="invalid_host")
    if host in _BLOCKED_HOSTS or host.endswith(".localhost"):
        raise PluginUrlError("不允許本機或 metadata 主機", code="blocked_host")
    if host in _METADATA_IPS:
        raise PluginUrlError("不允許雲端 metadata 位址", code="blocked_host")
    try:
        addr = ipaddress.ip_address(host)
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
        ):
            raise PluginUrlError("不允許私有、迴圈或鏈路本地位址", code="blocked_ip")
    except ValueError:
        if host == "localhost":
            raise PluginUrlError("不允許 localhost", code="blocked_host")
        _resolve_public_host(host)
    return raw


def _resolve_public_host(host: str) -> None:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise PluginUrlError(f"無法解析主機：{host}", code="dns_failed") from exc
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        ip_str = sockaddr[0]
        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or str(addr) in _METADATA_IPS
        ):
            raise PluginUrlError("URL 解析到私有或 metadata 位址", code="blocked_ip")


def probe_plugin(plugin_id: str) -> dict[str, Any]:
    entry = catalog_entry(plugin_id)
    if not entry:
        raise PluginUrlError(f"未知插件：{plugin_id}", code="unknown_plugin")
    settings = load_settings()
    stored = dict((settings.get("plugins") or {}).get(plugin_id) or {})
    map_url = str(stored.get("map_url") or "").strip()
    if not map_url:
        raise PluginUrlError("尚未設定地圖 URL", code="unconfigured")
    validated = validate_map_url(map_url)
    probe = _http_probe(validated)
    stored["last_probe"] = probe
    plugins = dict(settings.get("plugins") or {})
    plugins[plugin_id] = stored
    settings["plugins"] = plugins
    save_settings(settings)
    _append_observability_event(
        f"Minecraft 插件探測 {entry['name']} → {probe.get('status', 'unknown')}",
        {
            "kind": "minecraft_plugin",
            "plugin_id": plugin_id,
            "action": "probe",
            "ok": probe.get("ok"),
            "status": probe.get("status"),
            "status_code": probe.get("status_code"),
        },
    )
    return {
        "plugin_id": plugin_id,
        "map_url": validated,
        "probe": probe,
        "embeddable": bool(entry.get("embeddable")),
        "connection_status": _connection_status(entry, stored),
    }


def _http_probe(url: str) -> dict[str, Any]:
    checked_at = _now()
    result: dict[str, Any] = {
        "checked_at": checked_at,
        "url": url,
        "ok": False,
        "status": "unreachable",
        "status_code": None,
        "method": None,
        "error": None,
        "embeddable_hint": None,
    }
    headers = {"User-Agent": "Linkin-Minecraft-Plugin-Probe/1.0"}
    try:
        with httpx.Client(timeout=8.0, follow_redirects=True, headers=headers) as client:
            for method in ("HEAD", "GET"):
                try:
                    resp = client.request(method, url)
                    result["method"] = method
                    result["status_code"] = resp.status_code
                    result["ok"] = resp.status_code < 500
                    result["status"] = "reachable" if result["ok"] else "unreachable"
                    xfo = resp.headers.get("x-frame-options", "").lower()
                    csp = resp.headers.get("content-security-policy", "").lower()
                    if "deny" in xfo or "sameorigin" in xfo:
                        result["embeddable_hint"] = "x-frame-options 可能阻擋 iframe 嵌入，請改用反向代理同源路徑。"
                    elif "frame-ancestors" in csp and "'none'" in csp:
                        result["embeddable_hint"] = "CSP frame-ancestors 可能阻擋嵌入。"
                    else:
                        result["embeddable_hint"] = "可嘗試在面板內嵌；若失敗請以新分頁開啟或設定 nginx 反向代理。"
                    break
                except httpx.HTTPError:
                    continue
    except Exception as exc:
        result["error"] = str(exc)
    return result


def monitor_summary() -> dict[str, Any]:
    settings = load_settings()
    catalog = list_catalog()
    map_plugins = [p for p in catalog if p.get("category") == "map"]
    active = settings.get("active_map_plugin")
    map_url = _resolve_map_url(settings)
    statuses = {p["id"]: p.get("status") for p in map_plugins}
    return {
        "active_map_plugin": active,
        "map_url": map_url,
        "map_plugins": statuses,
        "configured_count": sum(1 for p in catalog if p.get("status") not in {"disabled", "unconfigured"}),
        "reachable_count": sum(1 for p in catalog if p.get("status") == "reachable"),
    }


def _append_observability_event(text: str, metadata: dict[str, Any]) -> None:
    try:
        get_store().upsert(
            COL_EVENTS,
            text,
            {**metadata, "source": "minecraft_plugins"},
            skip_quality=True,
        )
    except Exception as exc:
        logger.debug("無法寫入 Minecraft 插件觀測事件：%s", exc)


def reset_settings_cache() -> None:
    """測試用：刪除設定檔。"""
    path = settings_path()
    if path.is_file():
        path.unlink()
