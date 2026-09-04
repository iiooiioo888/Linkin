"""Sponge Schematic v1/v2/v3 編解碼與建築體素。"""

from __future__ import annotations

from backend.linkin.nbt import loads_gzip
from backend.linkin.schematic import (
    AIR,
    SPONGE_VERSION,
    Schematic,
    canonicalize_block,
    decode_schematic,
    encode_blockdata,
    encode_schematic,
    encode_varint,
    generate_structure,
    infer_kind,
    preview_payload,
    yzx_index,
)


def test_varint_roundtrip():
    for value in (0, 1, 127, 128, 255, 300, 16384):
        raw = encode_varint(value)
        assert raw
        decoded = __import__("backend.linkin.schematic", fromlist=["decode_varints"]).decode_varints(raw, 1)
        assert decoded == [value]


def test_yzx_order_matches_sponge_spec():
    width, length = 4, 5
    assert yzx_index(0, 0, 0, width, length) == 0
    assert yzx_index(3, 0, 0, width, length) == 3
    assert yzx_index(0, 0, 1, width, length) == 4
    assert yzx_index(0, 1, 0, width, length) == width * length


def test_v3_nested_root_and_blocks_container():
    model = generate_structure(
        prompt="月光庭园一座小桥",
        style="精灵古典",
        block_count=80,
        seed="v3-bridge",
        region="精灵森林",
    )
    raw = encode_schematic(model, version=3)
    assert raw[:2] == b"\x1f\x8b"
    root_name, root = loads_gzip(raw)
    assert root_name == ""
    assert "Schematic" in root
    body = root["Schematic"]
    assert int(body["Version"]) == 3
    assert "Palette" not in body
    assert "BlockData" not in body
    blocks = body["Blocks"]
    assert "Palette" in blocks
    assert "Data" in blocks
    biomes = body["Biomes"]
    assert "Palette" in biomes
    assert "minecraft:forest" in biomes["Palette"]
    restored = decode_schematic(raw)
    assert restored.version == 3
    assert restored.width == model.width
    assert restored.solid_count() == model.solid_count()
    assert restored.solid_count() > 0
    assert len(restored.biomes) == restored.volume()
    assert "minecraft:forest" in restored.biome_palette


def test_v3_preserves_block_states_and_block_entities():
    stairs = "minecraft:oak_stairs[facing=east,half=bottom]"
    model = Schematic(
        width=2,
        height=1,
        length=1,
        palette={AIR: 0, stairs: 1},
        blocks=[0, 1],
        block_entities=[{"Pos": [1, 0, 0], "Id": "minecraft:chest", "Data": {"CustomName": "demo"}}],
        biome_palette={"minecraft:plains": 0},
        biomes=[0, 0],
        kind="test",
    )
    restored = decode_schematic(encode_schematic(model, version=3))
    assert stairs in restored.palette
    assert canonicalize_block(stairs) == stairs
    solids = list(restored.iter_solid())
    assert solids == [(1, 0, 0, stairs)]
    assert restored.block_entities[0]["Id"] == "minecraft:chest"
    assert restored.block_entities[0]["Pos"] == [1, 0, 0]


def test_v2_file_still_reads_and_upgrades_2d_biomes():
    model = generate_structure(prompt="白石圣殿", style="白石圣殿", block_count=60, seed="v2")
    raw_v2 = encode_schematic(model, version=2)
    root_name, root = loads_gzip(raw_v2)
    assert root_name == "Schematic"
    assert int(root["Version"]) == 2
    assert "Palette" in root
    assert "BlockData" in root
    restored = decode_schematic(raw_v2)
    assert restored.version == 2
    assert restored.solid_count() == model.solid_count()
    assert len(restored.biomes) == restored.volume()

    upgraded = decode_schematic(encode_schematic(restored, version=3))
    assert upgraded.version == 3
    assert upgraded.solid_count() == restored.solid_count()


def test_preview_skips_air_and_keeps_colors():
    model = generate_structure(prompt="隐士木屋", style="隐士木屋", block_count=40, seed="house")
    payload = preview_payload(model, building_id="bld-test")
    assert payload["voxel_count"] == model.solid_count()
    assert payload["version"] == SPONGE_VERSION
    assert all("air" not in item["name"] for item in payload["palette"])
    assert all("color" in item for item in payload["palette"])
    assert infer_kind("雾中庭园一座隐所") == "house"


def test_encode_blockdata_uses_varint_for_large_palette_index():
    raw = encode_blockdata([0, 200])
    assert raw[0] == 0
    assert raw[1] & 0x80


def test_small_house_yzx_and_nbtlib_base64_roundtrip(tmp_path):
    from backend.linkin.schematic import (
        b64_to_schem_bytes,
        build_small_house_schematic,
        decode_schematic_base64,
        schematic_to_base64,
        yzx_index,
    )

    model = build_small_house_schematic()
    assert model.width == model.height == model.length == 3
    assert model.solid_count() == 27
    w, length = model.width, model.length
    inverse = model.names()
    assert inverse[model.blocks[yzx_index(1, 0, 1, w, length)]] == "minecraft:grass_block"
    assert inverse[model.blocks[yzx_index(0, 1, 0, w, length)]] == "minecraft:cobblestone"
    assert inverse[model.blocks[yzx_index(1, 1, 1, w, length)]] == "minecraft:oak_planks"

    raw = encode_schematic(model, version=3)
    assert raw[:2] == b"\x1f\x8b"
    root_name, root = loads_gzip(raw)
    assert root_name == ""
    assert int(root["Schematic"]["Version"]) == 3
    assert "Data" in root["Schematic"]["Blocks"]

    b64 = schematic_to_base64(model)
    assert b64.startswith("H4sI")
    wrapped = f"data:application/octet-stream;base64,\n{b64[:40]}\n{b64[40:]}"
    assert b64_to_schem_bytes(wrapped)[:2] == b"\x1f\x8b"
    restored = decode_schematic_base64(wrapped)
    assert restored.solid_count() == 27
    assert restored.width == 3

    out = tmp_path / "small_house.schem"
    out.write_bytes(raw)
    assert out.stat().st_size > 20
