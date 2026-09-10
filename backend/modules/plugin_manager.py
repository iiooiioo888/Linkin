"""插件生命週期管理（C-PLUGIN-001~003／TODO §6.2／§6.3）。

契約：
- C-PLUGIN-001：安裝／啟用為**顯式動作**；本模組刻意不提供任何
  串流完成／聊天 webhook 的自動安裝入口。
- C-PLUGIN-002：降級／停用**不丟失**已記錄呼叫日誌；審計讀取持久化軌跡，
  與插件當前可用性無關。
- C-PLUGIN-003：dsh-plugin 預設**手動 pin 版本**；僅白名單倉庫／已審核版本；
  禁止執行未審核遠端腳本。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

from backend.services.conversation_audit import InMemoryAuditTrailStore, PluginPin

logger = logging.getLogger(__name__)

# ── 錯誤碼 ──
ERR_PLUGIN_NOT_INSTALLED = "ERR_PLUGIN_NOT_INSTALLED"
ERR_PLUGIN_ALREADY_INSTALLED = "ERR_PLUGIN_ALREADY_INSTALLED"
ERR_PLUGIN_NOT_ENABLED = "ERR_PLUGIN_NOT_ENABLED"
ERR_PLUGIN_REPO_NOT_WHITELISTED = "ERR_PLUGIN_REPO_NOT_WHITELISTED"
ERR_PLUGIN_VERSION_NOT_REVIEWED = "ERR_PLUGIN_VERSION_NOT_REVIEWED"
ERR_PLUGIN_AUTO_INSTALL_FORBIDDEN = "ERR_PLUGIN_AUTO_INSTALL_FORBIDDEN"


class PluginStatus(str, Enum):
    INSTALLED = "installed"      # 已安裝未啟用
    ENABLED = "enabled"
    DISABLED = "disabled"        # 顯式停用
    DEGRADED = "degraded"        # 失敗降級（日誌保留）


@dataclass(frozen=True)
class PluginSourcePolicy:
    """dsh-plugin 來源政策（C-PLUGIN-003）。"""

    whitelisted_repos: frozenset[str] = frozenset({"deepseek-club/dsh-plugin"})
    reviewed_versions: frozenset[str] = frozenset()  # 已審核版本白名單
    default_pin_required: bool = True                # 預設手動 pin（禁止浮動版本）


@dataclass
class InstalledPlugin:
    plugin_id: str
    repo: str
    pin: PluginPin
    status: PluginStatus = PluginStatus.INSTALLED


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
        pin = PluginPin(plugin_id=plugin_id, pin_version=version, enabled=False)
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
        return self.trail_store.read(plugin_id)

    def plugin_set(self) -> list[PluginPin]:
        """給 C-AUDIT-004 快照雜湊用的當前插件集合。"""
        return [p.pin for p in self.plugins.values()]
