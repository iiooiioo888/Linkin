"""插件生命週期管理（C-PLUGIN-001~003／TODO §6.2／§6.3）。

契約：
- C-PLUGIN-001：安裝／啟用為**顯式動作**；本模組刻意不提供任何
  串流完成／聊天 webhook 的自動安裝入口。
- C-PLUGIN-002：降級／停用**不丟失**已記錄呼叫日誌；審計讀取持久化軌跡，
  與插件當前可用性無關。
- C-PLUGIN-003：dsh-plugin 預設**手動 pin 版本**；僅白名單倉庫／已審核版本；
  禁止執行未審核遠端腳本。

可視化插件（dsh-context 適配）：
- 倉庫 ``bowenliang123/dsh-context`` 已列入白名單；
- Linkin **不遠端拉取／執行** npm 包，而以本機 React 適配層
  （``ContextPanel``／``/context``）提供同等資訊架構；
- pin 版本寫死為 ``linkin-adapted``，安裝／啟用仍須顯式動作。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from backend.services.conversation_audit import InMemoryAuditTrailStore, PluginPin

logger = logging.getLogger(__name__)

# ── 錯誤碼 ──
ERR_PLUGIN_NOT_INSTALLED = "ERR_PLUGIN_NOT_INSTALLED"
ERR_PLUGIN_ALREADY_INSTALLED = "ERR_PLUGIN_ALREADY_INSTALLED"
ERR_PLUGIN_NOT_ENABLED = "ERR_PLUGIN_NOT_ENABLED"
ERR_PLUGIN_REPO_NOT_WHITELISTED = "ERR_PLUGIN_REPO_NOT_WHITELISTED"
ERR_PLUGIN_VERSION_NOT_REVIEWED = "ERR_PLUGIN_VERSION_NOT_REVIEWED"
ERR_PLUGIN_AUTO_INSTALL_FORBIDDEN = "ERR_PLUGIN_AUTO_INSTALL_FORBIDDEN"
ERR_PLUGIN_UNKNOWN_CATALOG = "ERR_PLUGIN_UNKNOWN_CATALOG"

# dsh-context 本機適配 pin（禁止浮動 latest）
DSH_CONTEXT_PLUGIN_ID = "dsh-context"
DSH_CONTEXT_REPO = "bowenliang123/dsh-context"
DSH_CONTEXT_PIN = "linkin-adapted"
DSH_CONTEXT_DOCS = "https://github.com/bowenliang123/dsh-context"

# 目錄：可適配的 dsh-plugin／可視化插件（預設未安裝；顯式安裝後才進 runtime）
PLUGIN_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "plugin_id": DSH_CONTEXT_PLUGIN_ID,
        "display_name": "Context 可視化",
        "repo": DSH_CONTEXT_REPO,
        "source_tag": "dsh-plugin",
        "default_pin": DSH_CONTEXT_PIN,
        "capability": "context_insight_ui",
        "kind": "visualization",
        "docs_url": DSH_CONTEXT_DOCS,
        "summary": (
            "Context 面板／瀏覽器／/context 命令：透視組成、演進、壓縮、剪枝事件與動作"
            "（Linkin 本機適配，對齊 dsh-context 資訊架構）。"
        ),
        "surfaces": ("chat_bottom", "context_modal", "monitor_mirror", "task_detail"),
        "commands": ("/context", "/context peek"),
        "remote_fetch": False,  # 禁止運行時拉取 npm／遠端腳本
    },
)


class PluginStatus(str, Enum):
    INSTALLED = "installed"      # 已安裝未啟用
    ENABLED = "enabled"
    DISABLED = "disabled"        # 顯式停用
    DEGRADED = "degraded"        # 失敗降級（日誌保留）


@dataclass(frozen=True)
class PluginSourcePolicy:
    """dsh-plugin 來源政策（C-PLUGIN-003）。"""

    whitelisted_repos: frozenset[str] = frozenset(
        {
            "deepseek-club/dsh-plugin",
            DSH_CONTEXT_REPO,
        }
    )
    # 空＝白名單倉庫內任意 pin 皆可；非空時僅允許列出版本（嚴格審核模式）
    reviewed_versions: frozenset[str] = frozenset()
    default_pin_required: bool = True                # 預設手動 pin（禁止浮動版本）


@dataclass
class InstalledPlugin:
    plugin_id: str
    repo: str
    pin: PluginPin
    status: PluginStatus = PluginStatus.INSTALLED
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class PluginManager:
    """插件安裝／啟用／停用／降級；全部為顯式動作。"""

    policy: PluginSourcePolicy = field(default_factory=PluginSourcePolicy)
    trail_store: InMemoryAuditTrailStore = field(default_factory=InMemoryAuditTrailStore)
    plugins: dict[str, InstalledPlugin] = field(default_factory=dict)

    # ── C-PLUGIN-003：安裝前來源校驗 ──

    def _check_source(self, repo: str, version: str | None) -> str | None:
        if repo not in self.policy.whitelisted_repos:
            return ERR_PLUGIN_REPO_NOT_WHITELISTED
        if version is None and self.policy.default_pin_required:
            # 預設手動 pin：不給版本＝浮動安裝 → 拒絕
            return ERR_PLUGIN_VERSION_NOT_REVIEWED
        if self.policy.reviewed_versions and version not in self.policy.reviewed_versions:
            return ERR_PLUGIN_VERSION_NOT_REVIEWED
        return None

    # ── C-PLUGIN-001：顯式安裝（僅此入口；無 on_stream_done 等自動觸發）──

    def install(self, plugin_id: str, repo: str, *, version: str | None) -> dict:
        """顯式安裝：必須由使用者／管理員動作觸發，且 pin 版本經來源校驗。"""
        if plugin_id in self.plugins:
            return {"ok": False, "error_code": ERR_PLUGIN_ALREADY_INSTALLED}
        err = self._check_source(repo, version)
        if err:
            return {"ok": False, "error_code": err}
        pin = PluginPin(plugin_id=plugin_id, pin_version=version or "", enabled=False)
        self.plugins[plugin_id] = InstalledPlugin(plugin_id=plugin_id, repo=repo, pin=pin)
        self.trail_store.append(plugin_id, {"type": "plugin_installed", "version": version})
        return {"ok": True, "status": PluginStatus.INSTALLED.value}

    def enable(self, plugin_id: str) -> dict:
        """顯式啟用。"""
        plugin = self.plugins.get(plugin_id)
        if plugin is None:
            return {"ok": False, "error_code": ERR_PLUGIN_NOT_INSTALLED}
        plugin.status = PluginStatus.ENABLED
        plugin.pin = PluginPin(plugin.plugin_id, plugin.pin.pin_version, True)
        self.trail_store.append(plugin_id, {"type": "plugin_enabled"})
        return {"ok": True, "status": plugin.status.value}

    # ── C-PLUGIN-002：停用／降級不丟軌跡 ──

    def disable(self, plugin_id: str) -> dict:
        plugin = self.plugins.get(plugin_id)
        if plugin is None:
            return {"ok": False, "error_code": ERR_PLUGIN_NOT_INSTALLED}
        plugin.status = PluginStatus.DISABLED
        plugin.pin = PluginPin(plugin.plugin_id, plugin.pin.pin_version, False)
        self.trail_store.append(plugin_id, {"type": "plugin_disabled"})
        return {"ok": True, "status": plugin.status.value}

    def record_call(self, plugin_id: str, payload: dict) -> dict:
        """插件呼叫記錄：只有啟用中可呼叫；記錄先於執行（降級後仍查得到）。"""
        plugin = self.plugins.get(plugin_id)
        if plugin is None:
            return {"ok": False, "error_code": ERR_PLUGIN_NOT_INSTALLED}
        if plugin.status is not PluginStatus.ENABLED:
            return {"ok": False, "error_code": ERR_PLUGIN_NOT_ENABLED}
        entry = {"type": "plugin_call", **payload}
        self.trail_store.append(plugin_id, entry)
        return {"ok": True}

    def degrade(self, plugin_id: str, *, reason: str) -> dict:
        """失敗降級：狀態改 degraded，**已記錄日誌全數保留**。"""
        plugin = self.plugins.get(plugin_id)
        if plugin is None:
            return {"ok": False, "error_code": ERR_PLUGIN_NOT_INSTALLED}
        plugin.status = PluginStatus.DEGRADED
        self.trail_store.append(plugin_id, {"type": "plugin_degraded", "reason": reason})
        return {"ok": True, "status": plugin.status.value}

    def audit_trail(self, plugin_id: str) -> list[dict]:
        """審計讀取持久化軌跡：與插件當前狀態（含降級／停用）無關。"""
        return list(self.trail_store.read(plugin_id))

    def plugin_set(self) -> list[PluginPin]:
        """給 C-AUDIT-004 快照雜湊用的當前插件集合。"""
        return [p.pin for p in self.plugins.values()]

    # ── 目錄／可視化插件（dsh-context）──

    def catalog(self) -> list[dict[str, Any]]:
        """可適配插件目錄（含安裝狀態；未安裝亦列出）。"""
        out: list[dict[str, Any]] = []
        for entry in PLUGIN_CATALOG:
            pid = str(entry["plugin_id"])
            installed = self.plugins.get(pid)
            row = dict(entry)
            row["surfaces"] = list(entry.get("surfaces") or ())
            row["commands"] = list(entry.get("commands") or ())
            if installed is None:
                row["status"] = "available"
                row["pin_version"] = entry.get("default_pin") or ""
                row["enabled"] = False
            else:
                row["status"] = installed.status.value
                row["pin_version"] = installed.pin.pin_version
                row["enabled"] = installed.status is PluginStatus.ENABLED
            out.append(row)
        return out

    def install_from_catalog(self, plugin_id: str) -> dict:
        """依目錄顯式安裝（使用目錄 default_pin；禁止遠端腳本）。"""
        entry = next((e for e in PLUGIN_CATALOG if e["plugin_id"] == plugin_id), None)
        if entry is None:
            return {"ok": False, "error_code": ERR_PLUGIN_UNKNOWN_CATALOG}
        if entry.get("remote_fetch"):
            return {"ok": False, "error_code": ERR_PLUGIN_AUTO_INSTALL_FORBIDDEN}
        version = str(entry.get("default_pin") or "")
        out = self.install(plugin_id, str(entry["repo"]), version=version or None)
        if out.get("ok"):
            self.plugins[plugin_id].meta = {
                "display_name": entry.get("display_name"),
                "kind": entry.get("kind"),
                "capability": entry.get("capability"),
                "docs_url": entry.get("docs_url"),
            }
        return out

    def list_installed(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for p in self.plugins.values():
            rows.append(
                {
                    "plugin_id": p.plugin_id,
                    "repo": p.repo,
                    "pin_version": p.pin.pin_version,
                    "enabled": p.pin.enabled,
                    "status": p.status.value,
                    **(p.meta or {}),
                }
            )
        return rows

    def is_enabled(self, plugin_id: str) -> bool:
        p = self.plugins.get(plugin_id)
        return bool(p and p.status is PluginStatus.ENABLED)


_MANAGER: PluginManager | None = None


def get_plugin_manager() -> PluginManager:
    """進程內單例（測試可經 ``reset_plugin_manager`` 清空）。"""
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = PluginManager()
    return _MANAGER


def reset_plugin_manager(manager: PluginManager | None = None) -> PluginManager:
    global _MANAGER
    _MANAGER = manager if manager is not None else PluginManager()
    return _MANAGER
