"""量化策略資金流視覺化測試。"""

from backend.company.quant_capital_flow_maps import strategy_capital_flow


def test_capital_flow_dual_ma():
    payload = strategy_capital_flow("dual_ma", symbol="600519", initial_capital=1_000_000)
    assert payload["ok"] is True
    assert payload["symbol"] == "600519"
    assert "waterfall_mermaid" in payload
    assert "state_machine_mermaid" in payload
    assert len(payload["timeline"]) >= 2
    assert "600519" in payload["waterfall_mermaid"]
    assert "雙均線" in payload["waterfall_mermaid"] or "dual_ma" in payload["name"].lower() or payload["name"]
    assert payload["profile"]["cash_buffer_pct"] + payload["profile"]["margin_pct"] + payload["profile"]["reserve_pct"] == 100


def test_capital_flow_composite_short():
    payload = strategy_capital_flow("composite", symbol="600519")
    assert payload["ok"] is True
    assert payload["profile"].get("short_enabled") is True
    assert "空頭持倉" in payload["waterfall_mermaid"]


def test_capital_flow_volatility_trailing():
    payload = strategy_capital_flow("atr_trail", symbol="600519", trailing_stop_pct=8.0)
    assert payload["ok"] is True
    assert "移動止損" in payload["state_machine_mermaid"] or "止損" in payload["state_machine_mermaid"]


def test_capital_flow_unknown():
    payload = strategy_capital_flow("not-a-strategy")
    assert payload["ok"] is False


def test_capital_flow_custom_stop():
    payload = strategy_capital_flow("rsi", stop_loss_pct=4.0, position_pct=60.0)
    assert payload["ok"] is True
    assert payload["profile"]["stop_loss_pct"] == 4.0
    assert payload["profile"]["position_pct"] == 60.0
