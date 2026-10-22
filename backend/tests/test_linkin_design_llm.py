"""LLM 建築設計層（design_llm）單元與 API 整合測試。

全部以 monkeypatch 隔離 LLM：無需真實 API 金鑰（AGENTS.md 約束 #2）。
"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.linkin import design_llm
from backend.linkin.constitution import reset_cache as reset_constitution_cache
from backend.linkin.design_llm import Design, compile_design, parse_design
from backend.linkin.knowledge import reset_store
from backend.linkin.schematic import canonicalize_block, decode_schematic

# ── fixtures ──


@pytest.fixture()
def linkin_env(tmp_path, monkeypatch):
    monkeypatch.setenv("EVOL_LINKIN_DATA_DIR", str(tmp_path / "linkin"))
    monkeypatch.setenv("EVOL_LINKIN_CONSTITUTION_PATH", str(tmp_path / "linkin_constitution.json"))
    monkeypatch.setenv("EVOL_LINKIN_CHROMA_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("EVOL_LINKIN_FORCE_JSON", "1")
    monkeypatch.setenv("EVOL_MC_MCP_ENABLED", "false")
    monkeypatch.setenv("EVOL_MC_MCP_TOKEN", "")
    monkeypatch.setenv("EVOL_MC_MCP_AUDIT_PATH", str(tmp_path / "mcp_audit.jsonl"))
    reset_store()
    reset_constitution_cache()
    yield
    reset_store()
    reset_constitution_cache()


@pytest.fixture()
def client(linkin_env):
    from backend.linkin.api import register_linkin

    app = FastAPI()
    register_linkin(app)
    return TestClient(app)


@pytest.fixture()
def llm_ready(monkeypatch):
    """強制 LLM 設計路徑可用，並回傳一個可設定回應的 fake call_llm 控制器。"""
    monkeypatch.setattr(design_llm, "_llm_ready", lambda: True)
    monkeypatch.delenv("EVOL_LINKIN_LLM_DESIGN", raising=False)
    state: dict = {"response": "", "calls": 0}

    def _fake_call_llm(prompt, system="", model=None, **kwargs):
        state["calls"] += 1
        state["last_prompt"] = prompt
        if isinstance(state["response"], Exception):
            raise state["response"]
        return state["response"]

    monkeypatch.setattr(design_llm, "call_llm", _fake_call_llm)
    return state


BRIDGE_DESIGN = {
    "kind": "bridge",
    "size": [9, 9, 21],
    "ops": [
        # 拱形橋體（沿 z 跨河的半圓拱）
        {"op": "arch", "x": 4, "y": 1, "z": 3, "span": 15, "height": 4, "material": "secondary", "axis": "z"},
        # 橋面
        {"op": "cuboid", "x": 2, "y": 5, "z": 0, "w": 5, "h": 1, "d": 21, "material": "primary"},
        # 兩側欄杆
        {"op": "line", "x1": 2, "y1": 6, "z1": 0, "x2": 2, "y2": 6, "z2": 20, "material": "trim"},
        {"op": "line", "x1": 6, "y1": 6, "z1": 0, "x2": 6, "y2": 6, "z2": 20, "material": "trim"},
        # 燈柱 ×2（柱 + 頂部發光方塊）→ 回應「要有燈柱」
        {"op": "column", "x": 2, "y": 6, "z": 4, "height": 3, "material": "trim"},
        {"op": "cuboid", "x": 2, "y": 9, "z": 4, "w": 1, "h": 1, "d": 1, "material": "accent"},
        {"op": "column", "x": 6, "y": 6, "z": 16, "height": 3, "material": "trim"},
    ],
}


def _design(ops, width=16, height=16, length=16, kind="pavilion", warnings=None):
    return Design(kind=kind, width=width, height=height, length=length, ops=ops, warnings=warnings or [])


def _solids(schematic):
    return {(x, y, z): name for x, y, z, name in schematic.iter_solid()}


def _compile(ops, *, style="月光庭园", budget=4096, width=16, height=16, length=16, kind="pavilion"):
    return compile_design(
        _design(ops, width=width, height=height, length=length, kind=kind),
        style=style,
        budget=budget,
        seed="test",
    )


# ── parse_design ──


def test_parse_design_valid_with_role_material():
    text = json.dumps(
        {
            "kind": "house",
            "size": [7, 5, 7],
            "ops": [
                {"op": "cuboid", "x": 0, "y": 0, "z": 0, "w": 7, "h": 1, "d": 7, "material": "floor"},
                {"op": "cuboid", "x": 0, "y": 1, "z": 0, "w": 7, "h": 3, "d": 7, "material": "minecraft:air"},
            ],
        },
        ensure_ascii=False,
    )
    design = parse_design(text, style="月光庭园", prompt="小屋")
    assert design is not None
    assert design.kind == "house"
    assert (design.width, design.height, design.length) == (7, 5, 7)
    assert len(design.ops) == 2
    # 角色名已解析為具體方塊
    assert design.ops[0]["material"] == canonicalize_block("minecraft:moss_block")
    assert design.ops[1]["material"] == "minecraft:air"
    assert design.warnings == []


def test_parse_design_accepts_code_fence_and_prefix_noise():
    text = "好的，這是設計：\n```json\n" + json.dumps(BRIDGE_DESIGN, ensure_ascii=False) + "\n```"
    design = parse_design(text, style="月光庭园", prompt="拱橋")
    assert design is not None
    assert design.kind == "bridge"
    assert len(design.ops) == 7


def test_parse_design_rejects_garbage():
    assert parse_design("我不確定該怎麼做", style="月光庭园") is None
    assert parse_design("", style="月光庭园") is None
    assert parse_design(json.dumps({"ops": []}), style="月光庭园") is None
    assert parse_design(json.dumps({"size": [5, 5, 5], "ops": "cuboid"}), style="月光庭园") is None


def test_parse_design_skips_invalid_ops_but_keeps_valid():
    text = json.dumps(
        {
            "kind": "tower",
            "size": [8, 8, 8],
            "ops": [
                {"op": "fly", "x": 0},  # 未知 op
                {"op": "cuboid", "x": 0, "y": 0, "z": 0, "w": 3, "h": 3, "d": 3, "material": "minecraft:bedrock"},  # 非白名單
                {"op": "cuboid", "x": 0, "y": 0, "z": 0, "w": 3, "h": 3, "d": 3},  # 缺 material
                {"op": "cuboid", "x": 0, "y": 0, "z": 0, "w": 3, "h": 3, "d": 3, "material": "primary"},  # 合法
            ],
        }
    )
    design = parse_design(text, style="月光庭园", prompt="塔")
    assert design is not None
    assert len(design.ops) == 1
    assert len(design.warnings) == 3


def test_parse_design_all_ops_invalid_returns_none():
    text = json.dumps(
        {"kind": "house", "size": [5, 5, 5], "ops": [{"op": "cuboid", "x": 0, "y": 0, "z": 0, "w": 1, "h": 1, "d": 1, "material": "minecraft:dragon_egg"}]}
    )
    assert parse_design(text, style="月光庭园") is None


def test_parse_design_truncates_ops_and_infers_kind():
    ops = [
        {"op": "cuboid", "x": 0, "y": 0, "z": 0, "w": 1, "h": 1, "d": 1, "material": "primary"}
        for _ in range(60)
    ]
    design = parse_design(json.dumps({"kind": "spaceship", "ops": ops}), style="月光庭园", prompt="蓋一座橋")
    assert design is not None
    assert len(design.ops) == design_llm.MAX_OPS
    assert design.kind == "bridge"  # 非法 kind → infer_kind(prompt)
    assert any("截斷" in w for w in design.warnings)


def test_parse_design_clamps_canvas_and_derives_size():
    text = json.dumps(
        {
            "size": [999, 2, 5],
            "ops": [{"op": "cuboid", "x": 1, "y": 0, "z": 1, "w": 4, "h": 3, "d": 4, "material": "stone"}],
        }
    )
    design = parse_design(text, style="月光庭园")
    assert design is not None
    assert design.width <= design_llm.MAX_DESIGN_AXIS  # 999 被 clamp
    # 缺 size 時由包圍盒推導：cuboid 至 (4, 2, 4) → 尺寸 (5, 3, 5)
    text2 = json.dumps(
        {"ops": [{"op": "cuboid", "x": 1, "y": 0, "z": 1, "w": 4, "h": 3, "d": 4, "material": "stone"}]}
    )
    design2 = parse_design(text2, style="月光庭园")
    assert design2 is not None
    assert (design2.width, design2.height, design2.length) == (5, 3, 5)


# ── 幾何編譯 ──


def test_compile_cuboid_solid_and_hollow_and_air_carve():
    solid = _compile([{"op": "cuboid", "x": 0, "y": 0, "z": 0, "w": 3, "h": 2, "d": 2, "material": "minecraft:stone"}])
    assert solid.solid_count() == 12

    hollow = _compile(
        [{"op": "cuboid", "x": 0, "y": 0, "z": 0, "w": 5, "h": 5, "d": 5, "material": "minecraft:stone", "hollow": True}],
        width=8, height=8, length=8,
    )
    assert hollow.solid_count() == 5**3 - 3**3  # 只有外殼

    carved = _compile(
        [
            {"op": "cuboid", "x": 0, "y": 0, "z": 0, "w": 3, "h": 3, "d": 3, "material": "minecraft:stone"},
            {"op": "cuboid", "x": 1, "y": 1, "z": 1, "w": 1, "h": 1, "d": 1, "material": "air"},
        ],
    )
    assert carved.solid_count() == 26


def test_compile_line_column():
    line = _compile([{"op": "line", "x1": 0, "y1": 0, "z1": 0, "x2": 4, "y2": 0, "z2": 0, "material": "minecraft:oak_planks"}])
    cells = _solids(line)
    assert set(cells) == {(i, 0, 0) for i in range(5)}

    diag = _compile([{"op": "line", "x1": 0, "y1": 0, "z1": 0, "x2": 2, "y2": 2, "z2": 2, "material": "minecraft:stone"}])
    assert set(_solids(diag)) == {(0, 0, 0), (1, 1, 1), (2, 2, 2)}

    column = _compile([{"op": "column", "x": 3, "y": 0, "z": 3, "height": 4, "radius": 0, "material": "minecraft:stone"}])
    assert set(_solids(column)) == {(3, i, 3) for i in range(4)}

    thick = _compile([{"op": "column", "x": 5, "y": 0, "z": 5, "height": 2, "radius": 1, "material": "minecraft:stone"}])
    # radius=1 → 每層十字 5 格
    assert thick.solid_count() == 10


def test_compile_arch_shape():
    arch = _compile(
        [{"op": "arch", "x": 0, "y": 0, "z": 2, "span": 5, "height": 2, "axis": "x", "material": "minecraft:stone_bricks"}],
        width=8, height=8, length=8,
    )
    cells = _solids(arch)
    # dy = round(2*sin(pi*i/4)) → [0, 1, 2, 1, 0]
    assert cells == {
        (0, 0, 2): "minecraft:stone_bricks",
        (1, 1, 2): "minecraft:stone_bricks",
        (2, 2, 2): "minecraft:stone_bricks",
        (3, 1, 2): "minecraft:stone_bricks",
        (4, 0, 2): "minecraft:stone_bricks",
    }


def test_compile_pyramid_and_gable():
    pyramid = _compile(
        [{"op": "pyramid", "x": 0, "y": 0, "z": 0, "w": 5, "d": 5, "height": 3, "material": "minecraft:sandstone"}],
        width=8, height=8, length=8,
    )
    assert pyramid.solid_count() == 25 + 9 + 1

    gable = _compile(
        [{"op": "gable", "x": 0, "y": 0, "z": 0, "w": 5, "d": 5, "height": 3, "material": "minecraft:oak_planks"}],
        width=8, height=8, length=8,
    )
    # k=0: 5×5；k=1: 5×3；k=2: 5×1
    assert gable.solid_count() == 25 + 15 + 5


def test_compile_respects_budget_with_trim():
    big = _compile(
        [{"op": "cuboid", "x": 0, "y": 0, "z": 0, "w": 40, "h": 40, "d": 40, "material": "minecraft:stone"}],
        budget=100, width=40, height=40, length=40,
    )
    assert big.solid_count() == 100


def test_compile_rejects_op_over_volume_cap_at_parse():
    text = json.dumps(
        {
            "size": [64, 64, 64],
            "ops": [{"op": "cuboid", "x": 0, "y": 0, "z": 0, "w": 64, "h": 64, "d": 64, "material": "stone"}],
        }
    )
    # 64³ 超過單 op 體積上限 → op 跳過 → 無合法 op → None
    assert parse_design(text, style="月光庭园") is None


# ── generate_llm_structure（LLM 路徑 + fallback）──


def test_generate_llm_structure_success(llm_ready):
    llm_ready["response"] = json.dumps(BRIDGE_DESIGN, ensure_ascii=False)
    out = design_llm.generate_llm_structure(
        prompt="在林冠間搭建一座月光庭園拱橋，要有燈柱",
        style="月光庭园",
        block_count=800,
        seed="bld-test",
        region="精灵森林",
    )
    assert out is not None
    schematic, payload = out
    assert llm_ready["calls"] == 1
    assert schematic.kind == "bridge"
    assert schematic.solid_count() > 0
    assert schematic.metadata.get("Author") == "Linkin-LLM"
    assert payload["kind"] == "bridge"
    assert payload["op_count"] == 7
    assert payload["ops"][0]["op"] == "arch"
    # 角色名 secondary 已解析為風格調色盤的具體方塊
    assert payload["ops"][0]["material"] == "minecraft:oak_planks"
    # 提示詞包含需求與調色盤
    assert "月光庭園拱橋" in llm_ready["last_prompt"]
    assert "primary" in llm_ready["last_prompt"]
    # biome 來自區域
    assert "minecraft:forest" in schematic.biome_palette


def test_generate_llm_structure_none_when_not_ready(monkeypatch):
    monkeypatch.setattr(design_llm, "_llm_ready", lambda: False)

    def _boom(*args, **kwargs):
        raise AssertionError("不該呼叫 call_llm")

    monkeypatch.setattr(design_llm, "call_llm", _boom)
    assert design_llm.generate_llm_structure(prompt="橋", style="月光庭园", block_count=100) is None


def test_generate_llm_structure_disabled_by_env(llm_ready, monkeypatch):
    monkeypatch.setenv("EVOL_LINKIN_LLM_DESIGN", "false")
    llm_ready["response"] = json.dumps(BRIDGE_DESIGN)
    assert design_llm.generate_llm_structure(prompt="橋", style="月光庭园", block_count=100) is None
    assert llm_ready["calls"] == 0


def test_generate_llm_structure_falls_back_on_bad_output(llm_ready):
    llm_ready["response"] = "抱歉，我无法生成 JSON。"
    assert design_llm.generate_llm_structure(prompt="橋", style="月光庭园", block_count=100) is None


def test_generate_llm_structure_falls_back_on_llm_error(llm_ready):
    llm_ready["response"] = RuntimeError("LLM 服務不可用")
    assert design_llm.generate_llm_structure(prompt="橋", style="月光庭园", block_count=100) is None


def test_generate_llm_structure_falls_back_on_empty_design(llm_ready):
    # 合法 JSON 但全部 op 都非法 → 編譯不出任何方塊
    llm_ready["response"] = json.dumps(
        {"kind": "house", "size": [5, 5, 5], "ops": [{"op": "cuboid", "x": 0, "y": 0, "z": 0, "w": 1, "h": 1, "d": 1, "material": "minecraft:void_air_x"}]}
    )
    assert design_llm.generate_llm_structure(prompt="屋", style="月光庭园", block_count=100) is None


# ── API 整合 ──


def test_api_generate_building_uses_llm_design(client, llm_ready):
    llm_ready["response"] = json.dumps(BRIDGE_DESIGN, ensure_ascii=False)
    r = client.post(
        "/linkin/buildings/generate",
        json={
            "prompt": "月光庭園拱橋，要有拱形橋體與燈柱",
            "style": "月光庭园",
            "location": "120, 64, -300",
            "region": "精灵森林",
            "block_count": 800,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    building = body["building"]
    assert building["generator"] == "llm"
    assert building["kind"] == "bridge"
    assert building["design"]["op_count"] == 7
    assert building["format"] == "sponge_schematic"
    assert building["block_count"] > 0
    # 預覽隨生成回傳
    assert body["preview"] is not None
    # .schem 可下載且可解碼
    bid = building["id"]
    r2 = client.get(f"/linkin/buildings/{bid}/schematic")
    assert r2.status_code == 200
    schem = decode_schematic(r2.content)
    # LLM 設計未超預算（161 ≤ 800），檔案方塊數與紀錄一致；Metadata 隨 NBT 往返
    assert schem.solid_count() == building["block_count"] > 100
    assert schem.metadata.get("Author") == "Linkin-LLM"


def test_api_generate_building_falls_back_to_procedural(client, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(design_llm, "_llm_ready", lambda: False)
    r = client.post(
        "/linkin/buildings/generate",
        json={
            "prompt": "月光庭園小橋",
            "style": "月光庭园",
            "location": "0, 64, 0",
            "block_count": 300,
        },
    )
    assert r.status_code == 200, r.text
    building = r.json()["building"]
    assert building["generator"] == "procedural"
    assert "design" not in building
    assert building["block_count"] > 0
