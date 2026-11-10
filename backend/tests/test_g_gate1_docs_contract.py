"""G-GATE1：宣導文件契約存在性（不測 runtime 閘行為）。"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CONTRACT = REPO / "docs" / "contracts" / "g-gate1-dual-gate.md"
WIRE = REPO / "docs" / "modelgw-wire.md"
FAQ = REPO / "docs" / "faq.md"


def test_g_gate1_contract_exists_and_keywords() -> None:
    text = CONTRACT.read_text(encoding="utf-8")
    assert "G-GATE1" in text
    assert "B 層產品濾鏡" in text or "B 層產品目錄濾鏡" in text
    assert "唯一" in text and ("準入權威" in text or "能不能叫" in text)
    assert "wire_change" in text and "none" in text
    assert "ready_to_merge=false" in text or "`ready_to_merge=false`" in text
    assert "Hub 拒 ≠ ModelGW 拒" in text


def test_g_gate1_wire_section_points_to_contract() -> None:
    text = WIRE.read_text(encoding="utf-8")
    assert "雙閘時序（G-GATE1）" in text
    assert "g-gate1-dual-gate.md" in text
    assert "Hub 拒 ≠ ModelGW 拒" in text


def test_g_gate1_faq_covers_hub_vs_modelgw() -> None:
    text = FAQ.read_text(encoding="utf-8")
    assert "G-GATE1" in text
    assert "準入權威" in text
    assert "繞過 ModelGW" in text or "繞過" in text
