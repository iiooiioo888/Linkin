"""指揮鏈席位表（Seat Table）schema。

對齊 TODO §2：把指揮鏈從隱式流程拆成**可配置席位**，並提供：

- ``SeatSpec``：席位契約欄位（§2.2）——角色 ID、顯示名、職責、Prompt 引用、
  工具範圍、**可呼叫插件白名單**、上下游邊界、可跳過／可並行、
  **最高可掛載插件來源層級**、**是否具備部署確認權**（§8.2）。
- ``SeatTable``：帶 ``schema_version`` 的席位表（§2.4）；舊任務在席位表變更時
  進入「凍結」或走強制遷移，禁止用新表默認改寫進行中 DAG。
- 插件掛載**雙向校驗**（§6.4）：席位白名單 ∩ 插件最高可掛載層級。

本模組是 `backend.company.roles.STANDARD_ROLES` 的**視圖層**：
不修改既有 ``RoleDefinition``（向後相容），僅派生席位契約。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping

from backend.company.state import RoleDefinition, RoleType

SEAT_TABLE_SCHEMA_VERSION = "1.0.0"


class PluginSource(str, Enum):
    """插件來源標籤（§6.1）。"""

    DEEPSEEK_CLUB = "deepseek-club"
    DSH_PLUGIN = "dsh-plugin"
    WORLD_MODULE = "world-module"


# RAHO 質詢層（L5 最高、L0 最低；support＝組織層支援席，掛載能力等同 L2 上限）
_RAHO_LAYER_ORDER: dict[str, int] = {
    "L5": 5,
    "L4": 4,
    "L3": 3,
    "L2": 2,
    "L1": 1,
    "L0": 0,
    "support": 2,  # 組織層支援席視同 L2 執行層級（可掛插件，受白名單約束）
}

# RoleType → RAHO 層（脊柱角色）；其餘為 support
_RAHO_SPINE: dict[RoleType, str] = {
    RoleType.REQUIREMENT_AUDITOR: "L4",
    RoleType.TACTICAL_COMMANDER: "L3",
    RoleType.ATOMIC_EXECUTOR: "L2",
    RoleType.CONSTITUTIONAL_INSPECTOR: "L1",
    RoleType.ENVIRONMENT_KERNEL: "L0",
}

# 部署確認權（§2.2／§8.2，寫死）：預設僅 L5 用戶與人類管理員。
# 這兩者不是 RoleType，而是席位表中的虛擬席位 ID。
DEPLOY_CONFIRM_SEATS: frozenset[str] = frozenset({"l5_user", "human_admin"})

# L0 注入席契約（§2.2／§4.1，寫死）：只做注入，無工具、無插件、不執行任務
_L0_FORBIDDEN = "L0 注入席不得持有工具或插件白名單（契約 C-SEAT-003）"


def raho_layer_rank(layer: str) -> int:
    """層級數值化；未知層級視為最低（最保守）。"""
    return _RAHO_LAYER_ORDER.get((layer or "").strip(), -1)


@dataclass(frozen=True)
class SeatSpec:
    """席位契約（§2.2）。immutable：席位表變更必走 schema_version 升版。"""

    role_id: str
    display_name: str
    raho_layer: str = "support"           # L5/L4/L3/L2/L1/L0/support
    responsibilities: tuple[str, ...] = ()
    prompt_ref: str = ""                  # Prompt／模板引用（不內嵌全文）
    tool_scope: tuple[str, ...] = ()      # 可呼叫工具／模組範圍
    plugin_whitelist: tuple[str, ...] = ()  # 可呼叫插件白名單（插件 ID）
    upstream: tuple[str, ...] = ()        # 上游邊界
    downstream: tuple[str, ...] = ()      # 下游邊界
    skippable: bool = False
    parallel: bool = False
    max_plugin_source_level: str = "L2"   # 最高可掛載插件來源層級
    deploy_confirm: bool = False          # §8.2 部署確認權

    def can_call_plugin(self, plugin_id: str) -> bool:
        return plugin_id in self.plugin_whitelist

    def to_dict(self) -> dict[str, Any]:
        return {
            "role_id": self.role_id,
            "display_name": self.display_name,
            "raho_layer": self.raho_layer,
            "responsibilities": list(self.responsibilities),
            "prompt_ref": self.prompt_ref,
            "tool_scope": list(self.tool_scope),
            "plugin_whitelist": list(self.plugin_whitelist),
            "upstream": list(self.upstream),
            "downstream": list(self.downstream),
            "skippable": self.skippable,
            "parallel": self.parallel,
            "max_plugin_source_level": self.max_plugin_source_level,
            "deploy_confirm": self.deploy_confirm,
        }


@dataclass(frozen=True)
class PluginMountPolicy:
    """插件掛載聲明（§2.4／§6.2）：來源標籤＋最高可掛載席位層級。"""

    plugin_id: str
    source: PluginSource
    max_mount_layer: str = "L2"           # 例：僅允許掛 L2 以下
    pin_version: str = ""                 # dsh-plugin 預設手動 pin（§6.2）

    def to_dict(self) -> dict[str, Any]:
        return {
            "plugin_id": self.plugin_id,
            "source": self.source.value,
            "max_mount_layer": self.max_mount_layer,
            "pin_version": self.pin_version,
        }


@dataclass(frozen=True)
class MountVerdict:
    ok: bool
    reason: str = ""


@dataclass(frozen=True)
class SeatTable:
    """席位表：帶 schema_version（§2.4）。舊任務凍結／遷移由調用方依版本判斷。"""

    schema_version: str
    seats: Mapping[str, SeatSpec] = field(default_factory=dict)

    def seat(self, role_id: str) -> SeatSpec | None:
        return self.seats.get(role_id)

    def check_plugin_mount(self, role_id: str, policy: PluginMountPolicy) -> MountVerdict:
        """雙向校驗（§6.4）：席位白名單 ∩ 插件最高可掛載層級 ∩ 來源層級上限。"""
        seat = self.seat(role_id)
        if seat is None:
            return MountVerdict(False, f"ERR_SEAT_UNKNOWN: 席位不存在 {role_id}")
        if seat.raho_layer == "L0":
            return MountVerdict(False, f"ERR_L0_NO_PLUGIN: {_L0_FORBIDDEN}")
        if not seat.can_call_plugin(policy.plugin_id):
            return MountVerdict(
                False,
                f"ERR_PLUGIN_NOT_WHITELISTED: {policy.plugin_id} 不在席位 {role_id} 白名單",
            )
        # 插件聲明的最高可掛載層級（如僅 L2 以下）
        if raho_layer_rank(seat.raho_layer) > raho_layer_rank(policy.max_mount_layer):
            return MountVerdict(
                False,
                f"ERR_PLUGIN_MOUNT_LEVEL: 席位層級 {seat.raho_layer} 高於插件上限 {policy.max_mount_layer}",
            )
        # 席位自身的插件來源層級上限（§2.2）
        if raho_layer_rank(policy.max_mount_layer) > raho_layer_rank(seat.max_plugin_source_level):
            return MountVerdict(
                False,
                f"ERR_SEAT_PLUGIN_SOURCE_LEVEL: 插件層級 {policy.max_mount_layer} 超過席位上限 {seat.max_plugin_source_level}",
            )
        return MountVerdict(True)

    def has_deploy_confirm(self, seat_id: str) -> bool:
        """§8.2：部署確認權。虛擬席位（l5_user/human_admin）恆具備。"""
        if seat_id in DEPLOY_CONFIRM_SEATS:
            return True
        seat = self.seat(seat_id)
        return bool(seat and seat.deploy_confirm)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "seats": {rid: spec.to_dict() for rid, spec in self.seats.items()},
        }


def _derive_seat(role: RoleDefinition) -> SeatSpec:
    """從既有 RoleDefinition 派生席位契約（不修改原定義）。"""
    raho_layer = _RAHO_SPINE.get(role.role_type, "support")
    deploy_confirm = False  # 預設僅 L5＋人類管理員（§2.2 寫死）
    if role.role_type is RoleType.ENVIRONMENT_KERNEL:
        # L0 注入席：無工具、無插件、不執行（§4.1）
        return SeatSpec(
            role_id=role.role_type.value,
            display_name=role.name,
            raho_layer="L0",
            responsibilities=tuple(role.responsibilities),
            prompt_ref=f"role:{role.role_type.value}",
            tool_scope=(),
            plugin_whitelist=(),
            upstream=(),
            downstream=(),
            skippable=False,
            parallel=False,
            max_plugin_source_level="L0",
            deploy_confirm=False,
        )
    return SeatSpec(
        role_id=role.role_type.value,
        display_name=role.name,
        raho_layer=raho_layer,
        responsibilities=tuple(role.responsibilities),
        prompt_ref=f"role:{role.role_type.value}",
        tool_scope=(),
        plugin_whitelist=(),
        upstream=(role.reporting_to.value,) if role.reporting_to else (),
        downstream=tuple(rt.value for rt in role.can_delegate_to),
        skippable=False,
        parallel=role.max_parallel_work > 1,
        max_plugin_source_level="L2",
        deploy_confirm=deploy_confirm,
    )


def build_default_seat_table(
    roles: Mapping[RoleType, RoleDefinition] | None = None,
    *,
    schema_version: str = SEAT_TABLE_SCHEMA_VERSION,
) -> SeatTable:
    """從 STANDARD_ROLES 派生預設席位表；呼叫方可注入自訂 roles 以便測試隔離。"""
    if roles is None:
        from backend.company.roles import STANDARD_ROLES

        roles = STANDARD_ROLES
    seats = {role.role_type.value: _derive_seat(role) for role in roles.values()}
    _validate_l0_invariant(seats.values())
    return SeatTable(schema_version=schema_version, seats=seats)


def _validate_l0_invariant(seats: Iterable[SeatSpec]) -> None:
    """契約 C-SEAT-003：L0 注入席不得持有工具／插件。"""
    for seat in seats:
        if seat.raho_layer == "L0" and (seat.tool_scope or seat.plugin_whitelist):
            raise ValueError(f"{_L0_FORBIDDEN}（席位 {seat.role_id}）")


def migrate_task_on_schema_change(old_version: str, new_version: str) -> str:
    """§2.4：席位表變更時的任務處置。寫死：版本不同 → 凍結（不靜默改寫 DAG）。"""
    if old_version == new_version:
        return "unchanged"
    return "frozen"  # 由呼叫方決定是否走顯式強制遷移 API
