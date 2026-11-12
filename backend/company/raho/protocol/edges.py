"""RAHO 身份與邊建構：raho_identity、邊標註、目錄／圖與上級層級。"""

from __future__ import annotations

from typing import Any

from backend.company.state import RoleType

from .labels import DIRECTION_LABELS, KIND_LABELS, LANE_LABELS, lane_label
from .layers import (
    COMMAND_CHAIN,
    INSPECT_CHAIN,
    KERNEL_CHAIN,
    LANE_COMMAND,
    LANE_INSPECT,
    LANE_LAYERS,
    LAYER_META,
    RAHO_CHAIN,
    RAHO_SPINE_ROLES,
    RahoLayer,
)
from .roles import _ROLE_OVERLAYS, _labels_for_ids, _role_value, role_to_raho_layer


def _make_edge(
    from_layer: int,
    to_layer: int,
    kind: str,
    label: str,
    direction: str,
) -> dict[str, Any]:
    src = LAYER_META[from_layer]
    dst = LAYER_META[to_layer]
    return {
        "from_layer": from_layer,
        "to_layer": to_layer,
        "from_role": src["role_id"],
        "to_role": dst["role_id"],
        "from_label": src["full"],
        "to_label": dst["full"],
        "kind": kind,
        "label": label,
        "direction": direction,
        "lane": src.get("lane") if direction == "inject" else (
            LANE_INSPECT if direction == "inspect" else LANE_COMMAND
        ),
    }


# 正規邊。up=質詢上級；down=指揮下達；inspect=L1 雙向審查；inject=L0 滲透。
GRILL_EDGES: tuple[dict[str, Any], ...] = (
    _make_edge(5, 4, "mandate", "提交需求", "down"),
    _make_edge(4, 3, "campaign", "戰術指令下達", "down"),
    _make_edge(3, 2, "campaign", "孵化原子任務", "down"),
    _make_edge(2, 1, "submit", "提交產出驗收", "inspect"),
    _make_edge(4, 5, "user_grill", "需求審計", "up"),
    _make_edge(3, 4, "escalate", "戰略不可行", "up"),
    _make_edge(3, 5, "escalate", "基礎設施缺失", "up"),
    _make_edge(2, 3, "mgp", "戰前質詢", "up"),
    _make_edge(2, 4, "escalate", "戰前逾時跳級", "up"),
    _make_edge(1, 2, "rework", "退回重做", "inspect"),
    _make_edge(1, 3, "inspect", "質疑規劃", "inspect"),
    _make_edge(1, 4, "escalate", "標準爭議", "up"),
    _make_edge(1, 5, "escalate", "最終裁定", "up"),
    _make_edge(0, 4, "l0", "滲透決策層", "inject"),
    _make_edge(0, 3, "l0", "滲透規劃層", "inject"),
    _make_edge(0, 2, "l0", "滲透執行層", "inject"),
    _make_edge(0, 1, "l0", "滲透審查層", "inject"),
)


def raho_identity(
    role: RoleType | str | None = None,
    layer: int | RahoLayer | None = None,
) -> dict[str, Any]:
    """質詢樹節點與角色名冊的統一身分。"""
    value = _role_value(role)
    overlay = _ROLE_OVERLAYS.get(value)
    resolved = int(overlay["layer"]) if overlay else (
        int(layer) if layer is not None else int(role_to_raho_layer(value or None))
    )
    if resolved not in LAYER_META:
        resolved = int(RahoLayer.L2_EXECUTOR)
    meta = LAYER_META[resolved]
    title = str(overlay["title"]) if overlay else str(meta["title"])
    role_id = value or str(meta["role_id"] or "atomic_executor")
    spine = bool(overlay["spine"]) if overlay else role_id in RAHO_SPINE_ROLES
    full = f"L{resolved} {title}"
    grill_targets = list(meta.get("grill_targets") or [])
    escalate_targets = list(meta.get("escalate_targets") or [])
    submit_targets = list(meta.get("submit_targets") or [])
    lane = str(meta.get("lane") or LANE_COMMAND)
    return {
        "layer": resolved,
        "role_id": role_id,
        "title": title,
        "short": f"L{resolved} {title[:2]}" if overlay and not spine else str(meta["short"]),
        "full": full,
        "spine": spine,
        "lane": lane,
        "lane_label": lane_label(lane),
        "independent": bool(meta.get("independent")),
        "reports_to": meta.get("reports_to"),
        "grill_targets": grill_targets,
        "grill_target_labels": _labels_for_ids(grill_targets),
        "escalate_targets": escalate_targets,
        "escalate_target_labels": _labels_for_ids(escalate_targets),
        "submit_targets": submit_targets,
        "submit_target_labels": _labels_for_ids(submit_targets),
    }


def annotate_edge(
    from_layer: int,
    to_layer: int,
    *,
    from_role: str = "",
    to_role: str = "",
) -> dict[str, str]:
    src = raho_identity(from_role or None, from_layer)
    dst = raho_identity(to_role or None, to_layer)
    return {
        "from_role": from_role or src["role_id"],
        "to_role": to_role or dst["role_id"],
        "from_label": src["full"],
        "to_label": dst["full"],
        "from_short": src["short"],
        "to_short": dst["short"],
    }


def attach_raho_fields(snapshot: dict[str, Any]) -> dict[str, Any]:
    """把 RAHO 身分寫進角色快照（名冊／工作台）。"""
    ident = raho_identity(snapshot.get("id"))
    name = str(snapshot.get("name") or "").strip()
    if name and not ident["spine"]:
        ident = {
            **ident,
            "title": name,
            "full": f"L{ident['layer']} {name}",
            "short": f"L{ident['layer']} {name[:4]}",
        }
    snapshot["raho_layer"] = ident["layer"]
    snapshot["raho_label"] = ident["full"]
    snapshot["raho_short"] = ident["short"]
    snapshot["raho_title"] = ident["title"]
    snapshot["raho_spine"] = ident["spine"]
    snapshot["raho_lane"] = ident["lane"]
    snapshot["raho_lane_label"] = ident["lane_label"]
    snapshot["grill_targets"] = ident["grill_targets"]
    snapshot["grill_target_labels"] = ident["grill_target_labels"]
    snapshot["reports_to"] = ident["reports_to"]
    snapshot["escalate_targets"] = ident["escalate_targets"]
    snapshot["escalate_target_labels"] = ident["escalate_target_labels"]
    snapshot["submit_targets"] = ident["submit_targets"]
    snapshot["submit_target_labels"] = ident["submit_target_labels"]
    snapshot["raho_independent"] = ident["independent"]
    return snapshot


def _decorate_layer(meta: dict[str, Any]) -> dict[str, Any]:
    row = dict(meta)
    row["lane_label"] = lane_label(row.get("lane"))
    row["grill_target_labels"] = _labels_for_ids(row.get("grill_targets"))
    row["escalate_target_labels"] = _labels_for_ids(row.get("escalate_targets"))
    row["submit_target_labels"] = _labels_for_ids(row.get("submit_targets"))
    return row


def raho_directory(*, include_kernel: bool = True) -> list[dict[str, Any]]:
    layers = (0, 1, 2, 3, 4, 5) if include_kernel else (1, 2, 3, 4, 5)
    return [_decorate_layer(LAYER_META[layer]) for layer in layers if layer in LAYER_META]


def grill_edges(*, include_inject: bool = True) -> list[dict[str, Any]]:
    edges = [dict(edge) for edge in GRILL_EDGES]
    if include_inject:
        return edges
    return [edge for edge in edges if edge.get("direction") != "inject"]


def raho_graph() -> dict[str, Any]:
    """質詢樹／名冊共用的完整圖：三條線、層級、邊。"""
    return {
        "chain": list(RAHO_CHAIN),
        "command_chain": list(COMMAND_CHAIN),
        "inspect_chain": list(INSPECT_CHAIN),
        "kernel_chain": list(KERNEL_CHAIN),
        "lanes": {
            key: {"id": key, "label": LANE_LABELS[key], "layers": list(layers)}
            for key, layers in LANE_LAYERS.items()
        },
        "layers": raho_directory(),
        "edges": grill_edges(),
        "kind_labels": dict(KIND_LABELS),
        "direction_labels": dict(DIRECTION_LABELS),
        "lane_labels": dict(LANE_LABELS),
    }


def superior_layer(layer: RahoLayer) -> RahoLayer:
    """質詢上拋的預設下一層。L1 跳過執行層直上 L4；L0 不參與質詢。"""
    if layer == RahoLayer.L0_KERNEL:
        return RahoLayer.L0_KERNEL
    if layer == RahoLayer.L1_INSPECTOR:
        return RahoLayer.L4_AUDITOR
    if layer >= RahoLayer.L5_USER:
        return RahoLayer.L5_USER
    return RahoLayer(int(layer) + 1)
