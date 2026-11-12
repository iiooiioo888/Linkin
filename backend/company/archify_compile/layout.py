"""版面連線 helper（自 backend.company.archify_compile 抽出）。

_named_connections／_grid_spine（同行／跨列正交連線）。
"""

from __future__ import annotations

import itertools
from typing import Any

from .labels import _compact, _short_label, _sid


def _named_connections(edges: list[dict[str, Any]], *, labeled: bool) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for i, edge in enumerate(edges):
        src, dst = _sid(edge["from"]), _sid(edge["to"])
        if src == dst or (src, dst) in seen:
            continue
        seen.add((src, dst))
        label = _short_label(edge.get("label") or "", 12) if labeled else ""
        out.append(
            _compact(
                {
                    "id": _sid(f"e{i}_{src}_{dst}"),
                    "from": src,
                    "to": dst,
                    "label": label or None,
                    "variant": "emphasis" if i == 0 else "default",
                }
            )
        )
    return out


def _grid_spine(components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """只連同行相鄰與每列第一顆，避免穿越節點。"""
    by_row: dict[int, list[dict[str, Any]]] = {}
    for node in components:
        by_row.setdefault(int(node["row"]), []).append(node)
    connections: list[dict[str, Any]] = []
    n = 0
    for row in sorted(by_row):
        items = sorted(by_row[row], key=lambda c: int(c["col"]))
        for left, right in itertools.pairwise(items):
            connections.append(
                {
                    "id": _sid(f"h{n}_{left['id']}_{right['id']}"),
                    "from": left["id"],
                    "to": right["id"],
                    "route": "orthogonal-h",
                }
            )
            n += 1
    rows = sorted(by_row)
    for upper, lower in itertools.pairwise(rows):
        a = min(by_row[upper], key=lambda c: int(c["col"]))
        b = min(by_row[lower], key=lambda c: int(c["col"]))
        if a["id"] == b["id"]:
            continue
        connections.append(
            {
                "id": _sid(f"v{n}_{a['id']}_{b['id']}"),
                "from": a["id"],
                "to": b["id"],
                "route": "orthogonal-v",
            }
        )
        n += 1
    return connections
