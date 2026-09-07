"""策略庫 Archify IR 測試。"""

from backend.company.quant_strategy_maps import (
    archify_strategies,
    strategy_catalog_maps,
    strategy_maps,
)


def test_catalog_maps_covers_all_categories_and_wired_engines():
    payload = strategy_catalog_maps()
    assert payload["ok"] is True
    assert payload["engine_count"] >= 29
    assert payload["overview"]["meta"]["type"] == "architecture"
    assert payload["data_flow"]["meta"]["type"] == "data-flow"
    assert payload["lifecycle"]["meta"]["type"] == "lifecycle"
    ids = {g["id"] for g in payload["groups"]}
    assert ids >= {"ma", "momentum", "mean_reversion", "breakout", "ml"}
    ma = next(g for g in payload["groups"] if g["id"] == "ma")
    node_ids = {n["id"] for n in ma["architecture"]["nodes"]}
    assert "dual_ma" in node_ids
    assert "hub_ma" in node_ids
    total_nodes = sum(len(g["items"]) for g in payload["groups"])
    assert total_nodes == payload["catalog_count"]


def test_strategy_maps_dual_ma_workflow():
    payload = strategy_maps("dual_ma")
    assert payload["ok"] is True
    assert payload["item"]["status"] == "wired"
    assert payload["workflow"]["meta"]["type"] == "workflow"
    assert any(n["id"] == "sma5" for n in payload["workflow"]["nodes"])
    assert payload["lifecycle"]["meta"]["type"] == "lifecycle"


def test_strategy_maps_enhanced_volume_workflow():
    payload = strategy_maps("enhanced_volume")
    assert payload["ok"] is True
    assert payload["workflow"]["meta"]["type"] == "workflow"
    ids = {n["id"] for n in payload["workflow"]["nodes"]}
    assert {"vol", "rsi", "bb", "kdj", "enh"} <= ids
    aliased = strategy_maps("EnhancedVolumeStrategy")
    assert aliased["ok"] is True
    assert aliased["item"]["engine"] == "enhanced_volume"


def test_strategy_maps_alias_and_unknown():
    aliased = strategy_maps("sma_cross_5_20")
    assert aliased["ok"] is True
    assert aliased["item"]["engine"] == "dual_ma"
    missing = strategy_maps("not-a-real-strategy")
    assert missing["ok"] is False


def test_archify_strategies_views():
    overview = archify_strategies("overview")
    assert overview["ok"] is True
    assert "groups" in overview
    group = archify_strategies("group", id="ma")
    assert group["ok"] is True
    assert group["ir"]["meta"]["category"] == "ma"
    flow = archify_strategies("data_flow")
    assert flow["ir"]["meta"]["type"] == "data-flow"
    one = archify_strategies("strategy", id="rsi")
    assert one["workflow"]["nodes"]
