"""Minecraft 四維情境快照（Phase 1：唯讀聚合）。

從既有資料源推導市況／經濟／地土／玩家四個維度，供 AI GM 與可觀測性注入。
無法誠實計算的指標標記為 unknown，不捏造數值。
"""

from __future__ import annotations

import math
import time
from collections import Counter
from typing import Any

_DIMENSIONS = frozenset({"market", "economy", "land", "players"})
_STUCK_QUEST_AGE_SECONDS = 3600.0
_TRADE_ACTIONS = frozenset({"pickup", "drop", "inventory", "chat"})
_ACTIVITY_WINDOW_SECONDS = 3600.0


def _dimension_block(
    *,
    status: str,
    signals: list[dict[str, Any]],
    summary: str,
    confidence: float,
) -> dict[str, Any]:
    conf = max(0.0, min(1.0, float(confidence)))
    return {
        "status": status,
        "signals": signals,
        "summary": summary,
        "confidence": round(conf, 2),
    }


def _signal(name: str, value: Any, *, unit: str | None = None, note: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"name": name, "value": value}
    if unit:
        out["unit"] = unit
    if note:
        out["note"] = note
    return out


def _unknown_signal(name: str, note: str = "資料不足") -> dict[str, Any]:
    return {"name": name, "value": "unknown", "note": note}


def _aggregate_inventory(players: list[dict[str, Any]]) -> dict[str, int]:
    totals: Counter[str] = Counter()
    for player in players:
        for item in player.get("inventory_summary") or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            try:
                count = int(item.get("count") or 0)
            except (TypeError, ValueError):
                count = 0
            if count > 0:
                totals[name] += count
    return dict(totals)


def _recent_player_events(*, since: float, actions: frozenset[str] | None = None) -> list[dict[str, Any]]:
    try:
        from backend.linkin.minecraft_observability import list_minecraft_events

        page = list_minecraft_events(since=since, limit=200, domain="player")
        rows = page.get("events") or []
        if actions:
            return [e for e in rows if str(e.get("action") or "") in actions]
        return rows
    except Exception:
        return []


def _build_market_dimension(
    *,
    items: list[dict[str, Any]],
    players_block: dict[str, Any],
    recent_trade_events: list[dict[str, Any]],
) -> dict[str, Any]:
    signals: list[dict[str, Any]] = []
    item_defs = [i for i in items if str(i.get("id") or i.get("name") or "").strip()]
    players = players_block.get("players") or []
    bridge_offline = bool(players_block.get("bridge_offline"))
    inv_totals = _aggregate_inventory(players)

    if item_defs:
        signals.append(_signal("item_catalog_count", len(item_defs), unit="items"))
    else:
        signals.append(_unknown_signal("item_catalog_count", "無道具目錄"))

    if bridge_offline and not inv_totals:
        signals.append(_unknown_signal("inventory_aggregate", "橋接離線，無背包聚合"))
        status = "unknown"
        confidence = 0.15
        summary = "無市況資料：道具目錄或玩家背包皆不可用。"
        return _dimension_block(status=status, signals=signals, summary=summary, confidence=confidence)

    if inv_totals:
        signals.append(_signal("unique_items_held", len(inv_totals), unit="kinds"))
        signals.append(_signal("total_items_held", sum(inv_totals.values()), unit="count"))
        if item_defs:
            defined_names = {
                str(i.get("name") or i.get("id") or "").strip().lower()
                for i in item_defs
                if str(i.get("name") or i.get("id") or "").strip()
            }
            held_names = {k.lower() for k in inv_totals}
            scarce = sorted(defined_names - held_names)
            signals.append(
                _signal(
                    "catalog_items_not_held",
                    len(scarce),
                    unit="kinds",
                    note="目錄有定義但無玩家在線持有（稀缺代理）",
                )
            )
            if scarce[:5]:
                signals.append(
                    _signal("scarce_examples", scarce[:5], note="範例（非價格指標）"),
                )
    elif not bridge_offline:
        signals.append(_signal("unique_items_held", 0, unit="kinds", note="在線玩家背包為空"))

    trade_count = len(recent_trade_events)
    signals.append(_signal("trade_related_events_1h", trade_count, unit="events"))
    if trade_count >= 12:
        heat = "high"
    elif trade_count >= 4:
        heat = "medium"
    elif trade_count > 0:
        heat = "low"
    else:
        heat = "unknown"
    signals.append(_signal("trade_heat", heat, note="以 pickup/drop/inventory/chat 事件代理"))

    has_catalog = bool(item_defs)
    has_inv = bool(inv_totals) or (not bridge_offline and players)
    if has_catalog and (has_inv or trade_count > 0):
        status = "ok"
        confidence = 0.65 if inv_totals else 0.45
    elif has_catalog or trade_count > 0:
        status = "partial"
        confidence = 0.4
    else:
        status = "unknown"
        confidence = 0.2

    parts: list[str] = []
    if inv_totals:
        parts.append(f"在線持有 {len(inv_totals)} 種道具")
    if item_defs:
        parts.append(f"目錄 {len(item_defs)} 項")
    if trade_count:
        parts.append(f"近 1h 交易相關事件 {trade_count}")
    if heat != "unknown":
        parts.append(f"交易熱度 {heat}")
    summary = "；".join(parts) if parts else "市況信號不足，無法判斷供需。"
    return _dimension_block(status=status, signals=signals, summary=summary, confidence=confidence)


def _optional_platform_credits() -> dict[str, Any] | None:
    """弱經濟代理：平台帳戶 credits（非遊戲內經濟）。讀取失敗則略過。"""
    try:
        from backend.billing.store import BillingStore

        store = BillingStore()
        # 無 request context 時無法得知 user_id；僅在全域可查時回傳
        return None
    except Exception:
        return None


def _build_economy_dimension(
    *,
    items: list[dict[str, Any]],
    quests: list[dict[str, Any]],
    players_block: dict[str, Any],
    pending_intents: dict[str, Any],
) -> dict[str, Any]:
    signals: list[dict[str, Any]] = []
    players = players_block.get("players") or []
    inv_by_player: list[int] = []
    for player in players:
        total = sum(int(i.get("count") or 0) for i in (player.get("inventory_summary") or []) if isinstance(i, dict))
        inv_by_player.append(total)

    if len(inv_by_player) >= 2:
        mean = sum(inv_by_player) / len(inv_by_player)
        variance = sum((x - mean) ** 2 for x in inv_by_player) / len(inv_by_player)
        signals.append(
            _signal(
                "inventory_count_variance",
                round(variance, 2),
                note="玩家背包總量方差（財富分布弱代理）",
            )
        )
        signals.append(_signal("inventory_count_spread", max(inv_by_player) - min(inv_by_player), unit="items"))
    elif players:
        signals.append(_signal("inventory_count_spread", 0, unit="items", note="僅一位在線玩家"))
    else:
        signals.append(_unknown_signal("inventory_count_variance", "無在線玩家背包"))

    reward_quests = [
        q
        for q in quests
        if q.get("reward") or q.get("rewards") or q.get("reward_items")
    ]
    if reward_quests:
        signals.append(_signal("quests_with_rewards_defined", len(reward_quests), unit="quests"))
    else:
        signals.append(_unknown_signal("in_world_reward_flow", "任務未定義獎勵欄位"))

    pending_count = int(pending_intents.get("count") or 0)
    signals.append(_signal("pending_world_intents", pending_count, unit="intents", note="待落地意圖（sink 代理）"))

    applied_items = sum(1 for i in items if str(i.get("world_status") or "") == "applied")
    pending_items = sum(1 for i in items if str(i.get("world_status") or "") in {"pending_world", "planned"})
    signals.append(_signal("items_applied", applied_items, unit="items"))
    signals.append(_signal("items_pending_world", pending_items, unit="items"))

    signals.append(_unknown_signal("price_index", "無遊戲內價格／通貨資料"))
    signals.append(_unknown_signal("inflation_rate", "無通膨指標"))

    platform = _optional_platform_credits()
    if platform:
        signals.append(
            _signal(
                "platform_credits_balance",
                platform.get("balance"),
                unit="platform_credits",
                note="Linkin 平台帳戶 credits，非遊戲內經濟",
            )
        )

    has_variance = len(inv_by_player) >= 2
    has_rewards = bool(reward_quests)
    if has_variance or has_rewards:
        status = "partial"
        confidence = 0.35 if has_variance else 0.25
    elif pending_count or applied_items:
        status = "partial"
        confidence = 0.3
    else:
        status = "unknown"
        confidence = 0.15

    parts: list[str] = []
    if has_variance:
        parts.append("背包量有玩家間差異")
    if reward_quests:
        parts.append(f"{len(reward_quests)} 個任務定義獎勵")
    if pending_count:
        parts.append(f"{pending_count} 筆待落地意圖")
    parts.append("無遊戲內通膨／價格指標")
    summary = "；".join(parts)
    return _dimension_block(status=status, signals=signals, summary=summary, confidence=confidence)


def _build_land_dimension(
    *,
    map_plans: list[dict[str, Any]],
    build_briefs: list[dict[str, Any]],
    layout_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    signals: list[dict[str, Any]] = []
    plan_count = len(map_plans)
    signals.append(_signal("map_plan_count", plan_count, unit="plans"))

    regions_with_plots: set[str] = set()
    plot_count = 0
    for plan in map_plans:
        region = str(plan.get("region") or plan.get("id") or "default")
        plots = plan.get("plots") or plan.get("features") or []
        if isinstance(plots, list) and plots:
            regions_with_plots.add(region)
            plot_count += len(plots)
    signals.append(_signal("map_regions_with_plots", len(regions_with_plots), unit="regions"))
    signals.append(_signal("map_plot_count", plot_count, unit="plots"))

    brief_by_status: Counter[str] = Counter()
    brief_regions: Counter[str] = Counter()
    for brief in build_briefs:
        st = str(brief.get("status") or "unknown")
        brief_by_status[st] += 1
        region = str(brief.get("region") or brief.get("map_region") or "unknown")
        brief_regions[region] += 1
    signals.append(_signal("build_brief_total", len(build_briefs), unit="briefs"))
    if brief_by_status:
        signals.append(_signal("build_brief_by_status", dict(brief_by_status)))

    pending_briefs = brief_by_status.get("pending_builder", 0) + brief_by_status.get("planned", 0)
    applied_briefs = brief_by_status.get("applied", 0) + brief_by_status.get("partial", 0)
    signals.append(_signal("build_briefs_pending", pending_briefs, unit="briefs"))
    signals.append(_signal("build_briefs_applied", applied_briefs, unit="briefs"))

    contested = sum(1 for c in brief_regions.values() if c > 1)
    empty_regions = max(0, len(regions_with_plots) - len(brief_regions))
    signals.append(_signal("regions_with_multiple_briefs", contested, note="多建築意圖區域"))
    signals.append(_signal("map_regions_without_briefs", empty_regions, note="有地圖區塊但無建築意圖"))

    if layout_summary:
        signals.append(_signal("layout_feature_count", layout_summary.get("feature_count"), unit="features"))
        signals.append(_signal("layout_has_map_plan", layout_summary.get("has_map_plan")))
        bounds = layout_summary.get("bounds")
        if isinstance(bounds, dict):
            try:
                span_x = abs(int(bounds.get("x2", 0)) - int(bounds.get("x1", 0)))
                span_z = abs(int(bounds.get("z2", 0)) - int(bounds.get("z1", 0)))
                signals.append(_signal("layout_span_blocks", max(span_x, span_z), unit="blocks"))
            except (TypeError, ValueError):
                pass
    else:
        signals.append(_unknown_signal("layout_feature_count", "無布局預覽"))

    if plan_count and (plot_count or build_briefs):
        status = "ok"
        confidence = 0.7
    elif plan_count or build_briefs or layout_summary:
        status = "partial"
        confidence = 0.5
    else:
        status = "unknown"
        confidence = 0.2

    parts: list[str] = []
    if plan_count:
        parts.append(f"{plan_count} 份地圖計畫")
    if plot_count:
        parts.append(f"{plot_count} 個地塊")
    if build_briefs:
        parts.append(f"{len(build_briefs)} 筆建築意圖（待處理 {pending_briefs}）")
    if layout_summary and layout_summary.get("feature_count"):
        parts.append(f"布局 {layout_summary['feature_count']} 要素")
    if contested:
        parts.append(f"{contested} 區域有多重建築意圖")
    summary = "；".join(parts) if parts else "地圖／建築資料不足。"
    return _dimension_block(status=status, signals=signals, summary=summary, confidence=confidence)


def _cluster_players(players: list[dict[str, Any]], *, radius: float = 32.0) -> dict[str, Any]:
    positions: list[tuple[str, float, float]] = []
    for player in players:
        pos = player.get("position")
        if not isinstance(pos, dict):
            continue
        x, z = pos.get("x"), pos.get("z")
        if x is None or z is None:
            continue
        try:
            positions.append((str(player.get("name") or "?"), float(x), float(z)))
        except (TypeError, ValueError):
            continue
    if len(positions) < 2:
        return {"clustered": False, "center": None, "count": len(positions)}
    cx = sum(p[1] for p in positions) / len(positions)
    cz = sum(p[2] for p in positions) / len(positions)
    max_dist = max(math.hypot(p[1] - cx, p[2] - cz) for p in positions)
    return {
        "clustered": max_dist <= radius,
        "center": {"x": round(cx), "z": round(cz)},
        "max_spread_blocks": round(max_dist, 1),
        "count": len(positions),
    }


def _stuck_quest_rows(active_rows: list[dict[str, Any]], *, now: float) -> list[dict[str, Any]]:
    stuck: list[dict[str, Any]] = []
    for row in active_rows:
        done = int(row.get("objectives_done") or 0)
        total = int(row.get("objectives_total") or 0)
        updated = float(row.get("updated_at") or row.get("started_at") or 0)
        age = now - updated if updated else 0.0
        no_progress = total > 0 and done == 0
        stale = age >= _STUCK_QUEST_AGE_SECONDS and done < total
        if no_progress or stale:
            stuck.append(
                {
                    "player_id": row.get("player_id"),
                    "quest_id": row.get("quest_id"),
                    "quest_title": row.get("quest_title"),
                    "objectives_done": done,
                    "objectives_total": total,
                    "age_seconds": round(age),
                }
            )
    return stuck


def _build_players_dimension(
    *,
    players_block: dict[str, Any],
    active_quest_rows: list[dict[str, Any]],
    recent_player_events: list[dict[str, Any]],
) -> dict[str, Any]:
    signals: list[dict[str, Any]] = []
    bridge_offline = bool(players_block.get("bridge_offline"))
    online_count = int(players_block.get("online_count") or 0)
    players = players_block.get("players") or []
    now = time.time()

    signals.append(_signal("online_count", online_count, unit="players"))
    signals.append(_signal("bridge_offline", bridge_offline))

    cluster = _cluster_players(players)
    if cluster["count"] >= 2:
        signals.append(_signal("position_clustered", cluster["clustered"]))
        if cluster.get("center"):
            signals.append(_signal("activity_hotspot_center", cluster["center"], unit="blocks"))
        signals.append(_signal("player_spread_blocks", cluster.get("max_spread_blocks"), unit="blocks"))
    elif online_count > 0:
        signals.append(_signal("position_clustered", True, note="僅一位在線"))
    else:
        signals.append(_unknown_signal("activity_hotspot", "無在線座標"))

    stuck = _stuck_quest_rows(active_quest_rows, now=now)
    signals.append(_signal("stuck_quest_count", len(stuck), unit="quests"))
    if stuck[:3]:
        signals.append(
            _signal(
                "stuck_quest_examples",
                [
                    f"{s['player_id']}:{s['quest_id']}({s['objectives_done']}/{s['objectives_total']})"
                    for s in stuck[:3]
                ],
            )
        )

    event_count = len(recent_player_events)
    rate = round(event_count / (_ACTIVITY_WINDOW_SECONDS / 3600.0), 2)
    signals.append(_signal("player_events_1h", event_count, unit="events"))
    signals.append(_signal("player_event_rate_per_hour", rate, unit="events/h"))

    action_counts = Counter(str(e.get("action") or "") for e in recent_player_events)
    if action_counts:
        top = action_counts.most_common(3)
        signals.append(_signal("top_player_actions_1h", [f"{a}:{c}" for a, c in top]))

    if bridge_offline and online_count == 0:
        status = "unknown" if not active_quest_rows and not recent_player_events else "partial"
        confidence = 0.25
    elif online_count > 0 or active_quest_rows or recent_player_events:
        status = "ok" if online_count > 0 else "partial"
        confidence = 0.75 if online_count > 0 else 0.45
    else:
        status = "unknown"
        confidence = 0.2

    parts: list[str] = []
    if bridge_offline:
        parts.append("橋接離線")
    parts.append(f"在線 {online_count} 人")
    if cluster["count"] >= 2 and cluster.get("center"):
        c = cluster["center"]
        parts.append(
            f"活動熱點 ({c['x']}, {c['z']})" if cluster["clustered"] else f"玩家分散（跨度 {cluster.get('max_spread_blocks')} 格）"
        )
    if stuck:
        parts.append(f"{len(stuck)} 個任務可能卡住")
    if event_count:
        parts.append(f"近 1h {event_count} 則玩家事件")
    summary = "；".join(parts) if parts else "玩家現場資料不足。"
    return _dimension_block(status=status, signals=signals, summary=summary, confidence=confidence)


def _build_hints(
    market: dict[str, Any],
    economy: dict[str, Any],
    land: dict[str, Any],
    players: dict[str, Any],
) -> list[str]:
    hints: list[str] = []

    def _sig_val(dim: dict[str, Any], name: str) -> Any:
        for s in dim.get("signals") or []:
            if s.get("name") == name:
                return s.get("value")
        return None

    stuck = _sig_val(players, "stuck_quest_count")
    if isinstance(stuck, int) and stuck > 0:
        examples = _sig_val(players, "stuck_quest_examples")
        ex = ""
        if isinstance(examples, list) and examples:
            ex = f"（如 {examples[0]}）"
        hints.append(f"{stuck} 位玩家任務可能卡住{ex}，考慮 hint 或 npc_say 引導")

    heat = _sig_val(market, "trade_heat")
    if heat == "high":
        hints.append("交易活動頻繁，NPC 回應可提及市場／道具流通")
    elif heat == "low":
        hints.append("市場活動偏低，可透過任務或提示刺激互動")

    scarce = _sig_val(market, "catalog_items_not_held")
    if isinstance(scarce, int) and scarce > 0:
        hints.append(f"目錄中 {scarce} 種道具無人持有，敘事可強調稀缺")

    pending_briefs = _sig_val(land, "build_briefs_pending")
    if isinstance(pending_briefs, int) and pending_briefs > 0:
        hints.append(f"尚有 {pending_briefs} 筆待建築意圖，地土開發壓力偏高")

    empty = _sig_val(land, "map_regions_without_briefs")
    if isinstance(empty, int) and empty > 0:
        hints.append(f"{empty} 個地圖區塊尚無建築意圖，可引導玩家探索空地")

    online = _sig_val(players, "online_count")
    if online == 0:
        hints.append("目前無在線玩家，優先 noop 或記錄情境備查")
    elif isinstance(online, int) and online >= 3:
        hints.append("多人在線，回應宜簡短並避免刷屏")

    hotspot = _sig_val(players, "activity_hotspot_center")
    if isinstance(hotspot, dict):
        hints.append(f"玩家聚集於 ({hotspot.get('x')}, {hotspot.get('z')})，事件可連結該區域任務")

    pending_intents = _sig_val(economy, "pending_world_intents")
    if isinstance(pending_intents, int) and pending_intents > 0:
        hints.append(f"{pending_intents} 筆世界意圖待落地，經濟／內容 sink 尚未完成")

    if economy.get("status") == "unknown":
        hints.append("經濟指標不足，勿假設通膨或物價")

    if not hints:
        hints.append("情境信號有限，保守選擇 noop 或簡短 hint")

    return hints[:8]


def build_situation_snapshot() -> dict[str, Any]:
    """聚合四維情境快照（唯讀）。"""
    from backend.linkin.knowledge import list_entities
    from backend.linkin.narrative_world_apply import list_pending_intents

    now = time.time()
    since = now - _ACTIVITY_WINDOW_SECONDS

    items = list_entities("items")
    quests = list_entities("quests")
    map_plans = list_entities("map_plans")
    build_briefs = list_entities("build_briefs")
    pending_intents = list_pending_intents()

    players_block: dict[str, Any] = {}
    try:
        from backend.linkin.minecraft_players import build_players_ai_block

        players_block = build_players_ai_block(max_players=16, max_events=0)
    except Exception:
        players_block = {"bridge_offline": True, "online_count": 0, "players": []}

    layout_summary: dict[str, Any] | None = None
    try:
        from backend.linkin.layout_preview import build_layout_preview

        preview = build_layout_preview()
        if not preview.get("empty"):
            raw = preview.get("layout_summary")
            layout_summary = raw if isinstance(raw, dict) else None
    except Exception:
        layout_summary = None

    active_quest_rows: list[dict[str, Any]] = []
    try:
        from backend.linkin.quest_runtime import build_active_quests_summary

        active_quest_rows = build_active_quests_summary(limit=20)
    except Exception:
        active_quest_rows = []

    recent_player = _recent_player_events(since=since)
    recent_trade = _recent_player_events(since=since, actions=_TRADE_ACTIONS)

    market = _build_market_dimension(items=items, players_block=players_block, recent_trade_events=recent_trade)
    economy = _build_economy_dimension(
        items=items,
        quests=quests,
        players_block=players_block,
        pending_intents=pending_intents,
    )
    land = _build_land_dimension(
        map_plans=map_plans,
        build_briefs=build_briefs,
        layout_summary=layout_summary,
    )
    players_dim = _build_players_dimension(
        players_block=players_block,
        active_quest_rows=active_quest_rows,
        recent_player_events=recent_player,
    )

    hints = _build_hints(market, economy, land, players_dim)

    snap = {
        "generated_at": now,
        "market": market,
        "economy": economy,
        "land": land,
        "players": players_dim,
        "hints": hints,
    }

    try:
        from backend.linkin.minecraft_situation_rules import (
            enrich_situation_snapshot,
            rules_enabled,
        )

        if rules_enabled():
            return enrich_situation_snapshot(snap)
    except Exception:
        pass
    return snap


def build_situation_dimension(dimension: str) -> dict[str, Any] | None:
    """回傳單一維度區塊；未知維度回傳 None。"""
    key = str(dimension or "").strip().lower()
    if key not in _DIMENSIONS:
        return None
    snap = build_situation_snapshot()
    block = snap.get(key)
    if not isinstance(block, dict):
        return None
    return {
        "generated_at": snap.get("generated_at"),
        "dimension": key,
        **block,
    }


def compact_situation_for_context(snap: dict[str, Any] | None = None) -> dict[str, Any]:
    """精簡版供 prompt／context 注入。"""
    full = snap or build_situation_snapshot()
    compact: dict[str, Any] = {"generated_at": full.get("generated_at"), "hints": full.get("hints") or []}
    if full.get("rule_recommendations"):
        compact["rule_recommendations"] = full.get("rule_recommendations")
    if full.get("region_focus"):
        compact["region_focus"] = full.get("region_focus")
    for dim in ("market", "economy", "land", "players"):
        block = full.get(dim) or {}
        compact[dim] = {
            "status": block.get("status"),
            "summary": block.get("summary"),
            "confidence": block.get("confidence"),
            "signals": [
                {"name": s.get("name"), "value": s.get("value")}
                for s in (block.get("signals") or [])[:6]
                if isinstance(s, dict)
            ],
        }
    return compact


__all__ = [
    "build_situation_dimension",
    "build_situation_snapshot",
    "compact_situation_for_context",
]
