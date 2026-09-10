"""Sponge Schematic（.schem）編解碼與建築體素生成。

.schem = Gzip 壓縮的 NBT。預設寫出 **Version 3**（WorldEdit / FAWE 現行標準）：
根複合標籤內嵌 ``Schematic``，方塊在 ``Blocks.{Palette,Data,BlockEntities}``，
生物群系為與方塊同體積的 **3D** ``Biomes.{Palette,Data}``。

仍可讀取 Version 1 / 2（根層 Palette + BlockData，以及 v2 的 2D 生物群系），
並在匯入時升級為 v3。BlockData 為 YZX 順序的 Minecraft VarInt 調色板索引。

寫出時使用 **nbtlib**（Gzip Java NBT），並可輸出 Base64 供無法直接傳檔時貼上。
"""

from __future__ import annotations

import base64
import hashlib
import random
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.linkin import nbt
from backend.linkin.knowledge import data_dir
from backend.linkin.schem_nbtlib import dumps_gzip as nbtlib_dumps_gzip
from backend.linkin.tools import MAX_BLOCKS

SPONGE_VERSION = 3
SPONGE_VERSION_V2 = 2
DEFAULT_DATA_VERSION = 3955  # Minecraft 1.21.x
AIR = "minecraft:air"
DEFAULT_BIOME = "minecraft:plains"
MAX_AXIS = 128
MAX_IMPORT_BYTES = 2 * 1024 * 1024

REGION_BIOMES: dict[str, str] = {
    "精灵森林": "minecraft:forest",
    "织庭都": "minecraft:plains",
    "裂隙港": "minecraft:stony_shore",
    "宁渊谷": "minecraft:swamp",
}

STYLE_PALETTES: dict[str, dict[str, str]] = {
    "精灵古典": {
        "primary": "minecraft:oak_planks",
        "secondary": "minecraft:oak_log",
        "accent": "minecraft:lantern",
        "roof": "minecraft:dark_oak_planks",
        "floor": "minecraft:moss_block",
        "trim": "minecraft:stripped_oak_wood",
        "fill": "minecraft:oak_leaves",
    },
    "林冠木石": {
        "primary": "minecraft:mossy_cobblestone",
        "secondary": "minecraft:cobblestone",
        "accent": "minecraft:glow_lichen",
        "roof": "minecraft:oak_leaves",
        "floor": "minecraft:moss_block",
        "trim": "minecraft:oak_log",
        "fill": "minecraft:vine",
    },
    "月光庭园": {
        "primary": "minecraft:smooth_quartz",
        "secondary": "minecraft:oak_planks",
        "accent": "minecraft:sea_lantern",
        "roof": "minecraft:white_wool",
        "floor": "minecraft:moss_block",
        "trim": "minecraft:calcite",
        "fill": "minecraft:flowering_azalea_leaves",
    },
    "树桥聚落": {
        "primary": "minecraft:jungle_planks",
        "secondary": "minecraft:jungle_log",
        "accent": "minecraft:lantern",
        "roof": "minecraft:jungle_leaves",
        "floor": "minecraft:stripped_jungle_wood",
        "trim": "minecraft:vine",
        "fill": "minecraft:moss_block",
    },
    "织梦典章": {
        "primary": "minecraft:quartz_block",
        "secondary": "minecraft:smooth_stone",
        "accent": "minecraft:gold_block",
        "roof": "minecraft:white_terracotta",
        "floor": "minecraft:polished_diorite",
        "trim": "minecraft:gold_block",
        "fill": "minecraft:bookshelf",
    },
    "白石圣殿": {
        "primary": "minecraft:quartz_block",
        "secondary": "minecraft:calcite",
        "accent": "minecraft:sea_lantern",
        "roof": "minecraft:smooth_quartz",
        "floor": "minecraft:smooth_stone",
        "trim": "minecraft:iron_block",
        "fill": "minecraft:white_wool",
    },
    "契约广场": {
        "primary": "minecraft:smooth_stone",
        "secondary": "minecraft:stone_bricks",
        "accent": "minecraft:lantern",
        "roof": "minecraft:polished_andesite",
        "floor": "minecraft:stone",
        "trim": "minecraft:chiseled_stone_bricks",
        "fill": "minecraft:cobblestone",
    },
    "金线回廊": {
        "primary": "minecraft:sandstone",
        "secondary": "minecraft:cut_sandstone",
        "accent": "minecraft:gold_block",
        "roof": "minecraft:yellow_terracotta",
        "floor": "minecraft:smooth_sandstone",
        "trim": "minecraft:gold_block",
        "fill": "minecraft:yellow_wool",
    },
    "蒸汽帆索": {
        "primary": "minecraft:copper_block",
        "secondary": "minecraft:spruce_planks",
        "accent": "minecraft:redstone_lamp",
        "roof": "minecraft:oxidized_copper",
        "floor": "minecraft:spruce_planks",
        "trim": "minecraft:iron_block",
        "fill": "minecraft:barrel",
    },
    "自由贸易港": {
        "primary": "minecraft:spruce_planks",
        "secondary": "minecraft:stripped_spruce_wood",
        "accent": "minecraft:lantern",
        "roof": "minecraft:dark_oak_planks",
        "floor": "minecraft:oak_planks",
        "trim": "minecraft:oak_log",
        "fill": "minecraft:barrel",
    },
    "裂隙工坊": {
        "primary": "minecraft:iron_block",
        "secondary": "minecraft:stone",
        "accent": "minecraft:redstone_lamp",
        "roof": "minecraft:deepslate_bricks",
        "floor": "minecraft:smooth_stone",
        "trim": "minecraft:copper_block",
        "fill": "minecraft:blast_furnace",
    },
    "黄铜市集": {
        "primary": "minecraft:copper_block",
        "secondary": "minecraft:stripped_oak_wood",
        "accent": "minecraft:lantern",
        "roof": "minecraft:terracotta",
        "floor": "minecraft:smooth_stone",
        "trim": "minecraft:raw_gold_block",
        "fill": "minecraft:barrel",
    },
    "水雾苔石": {
        "primary": "minecraft:moss_block",
        "secondary": "minecraft:mossy_stone_bricks",
        "accent": "minecraft:sea_lantern",
        "roof": "minecraft:oak_leaves",
        "floor": "minecraft:mossy_cobblestone",
        "trim": "minecraft:prismarine",
        "fill": "minecraft:water",
    },
    "隐士木屋": {
        "primary": "minecraft:dark_oak_planks",
        "secondary": "minecraft:dark_oak_log",
        "accent": "minecraft:lantern",
        "roof": "minecraft:spruce_planks",
        "floor": "minecraft:coarse_dirt",
        "trim": "minecraft:cobblestone",
        "fill": "minecraft:bookshelf",
    },
    "灵脉神殿": {
        "primary": "minecraft:prismarine",
        "secondary": "minecraft:dark_prismarine",
        "accent": "minecraft:sea_lantern",
        "roof": "minecraft:prismarine_bricks",
        "floor": "minecraft:smooth_stone",
        "trim": "minecraft:gold_block",
        "fill": "minecraft:water",
    },
    "雾中庭园": {
        "primary": "minecraft:moss_block",
        "secondary": "minecraft:oak_log",
        "accent": "minecraft:lantern",
        "roof": "minecraft:azalea_leaves",
        "floor": "minecraft:grass_block",
        "trim": "minecraft:cobblestone",
        "fill": "minecraft:flowering_azalea",
    },
}

DEFAULT_PALETTE = STYLE_PALETTES["精灵古典"]

BLOCK_COLORS: dict[str, dict[str, str | float]] = {
    "air": {"color": "#000000", "opacity": 0},
    "oak_planks": {"color": "#c29d62"},
    "spruce_planks": {"color": "#6e512e"},
    "dark_oak_planks": {"color": "#3e2912"},
    "jungle_planks": {"color": "#9a6d32"},
    "oak_log": {"color": "#6b512e"},
    "jungle_log": {"color": "#554319"},
    "dark_oak_log": {"color": "#2c1b0c"},
    "stripped_oak_wood": {"color": "#b8945a"},
    "stripped_spruce_wood": {"color": "#745a34"},
    "stripped_jungle_wood": {"color": "#ac8554"},
    "oak_leaves": {"color": "#3f7a2c", "opacity": 0.92},
    "jungle_leaves": {"color": "#2f6b24", "opacity": 0.92},
    "azalea_leaves": {"color": "#4c8a33", "opacity": 0.92},
    "flowering_azalea_leaves": {"color": "#5b9448", "opacity": 0.92},
    "flowering_azalea": {"color": "#d98aa8"},
    "moss_block": {"color": "#5a8c3e"},
    "mossy_cobblestone": {"color": "#738454"},
    "mossy_stone_bricks": {"color": "#6e7b5c"},
    "cobblestone": {"color": "#7a7a7a"},
    "stone": {"color": "#8a8a8a"},
    "smooth_stone": {"color": "#a6a6a6"},
    "stone_bricks": {"color": "#7a7a7a"},
    "chiseled_stone_bricks": {"color": "#6e6e6e"},
    "polished_andesite": {"color": "#82827c"},
    "polished_diorite": {"color": "#c5c5c1"},
    "quartz_block": {"color": "#ece6de"},
    "smooth_quartz": {"color": "#f0ebe4"},
    "calcite": {"color": "#e6e4dc"},
    "white_wool": {"color": "#f4f4f4"},
    "white_terracotta": {"color": "#d1b9a8"},
    "yellow_terracotta": {"color": "#ba8523"},
    "yellow_wool": {"color": "#e8c547"},
    "terracotta": {"color": "#985e43"},
    "sandstone": {"color": "#d8cb8a"},
    "cut_sandstone": {"color": "#d4c48a"},
    "smooth_sandstone": {"color": "#e0d29a"},
    "gold_block": {"color": "#f7c940"},
    "raw_gold_block": {"color": "#d6a84a"},
    "iron_block": {"color": "#d8d8d8"},
    "copper_block": {"color": "#c56c4a"},
    "oxidized_copper": {"color": "#53a486"},
    "prismarine": {"color": "#5a9b8a"},
    "prismarine_bricks": {"color": "#5c9b8e"},
    "dark_prismarine": {"color": "#345b52"},
    "sea_lantern": {"color": "#d5f2ee", "emissive": "#9ee7dc"},
    "lantern": {"color": "#c98a2a", "emissive": "#ffb347"},
    "redstone_lamp": {"color": "#9a6a3a", "emissive": "#e09a40"},
    "glow_lichen": {"color": "#738a6a", "emissive": "#8fbf7a", "opacity": 0.85},
    "water": {"color": "#3d6fbf", "opacity": 0.62},
    "grass_block": {"color": "#5d9b3e"},
    "coarse_dirt": {"color": "#4d3b2a"},
    "bookshelf": {"color": "#6b4a2a"},
    "barrel": {"color": "#8a6238"},
    "blast_furnace": {"color": "#4a4a4a"},
    "deepslate_bricks": {"color": "#4b4f55"},
    "vine": {"color": "#3d6b2a", "opacity": 0.8},
}


class SchematicError(ValueError):
    """Sponge Schematic 無法解析或超出限制。"""


@dataclass
class Schematic:
    width: int
    height: int
    length: int
    palette: dict[str, int]
    blocks: list[int]
    version: int = SPONGE_VERSION
    data_version: int = DEFAULT_DATA_VERSION
    offset: tuple[int, int, int] = (0, 0, 0)
    metadata: dict[str, Any] = field(default_factory=dict)
    kind: str = "pavilion"
    biome_palette: dict[str, int] = field(default_factory=dict)
    biomes: list[int] = field(default_factory=list)
    block_entities: list[dict[str, Any]] = field(default_factory=list)
    entities: list[dict[str, Any]] = field(default_factory=list)

    def volume(self) -> int:
        return int(self.width) * int(self.height) * int(self.length)

    def names(self) -> dict[int, str]:
        return {int(idx): str(name) for name, idx in self.palette.items()}

    def solid_count(self) -> int:
        inverse = self.names()
        return sum(1 for idx in self.blocks if not is_air(inverse.get(idx, AIR)))

    def iter_solid(self) -> Iterable[tuple[int, int, int, str]]:
        inverse = self.names()
        w, h, l = self.width, self.height, self.length
        for y in range(h):
            for z in range(l):
                for x in range(w):
                    idx = self.blocks[yzx_index(x, y, z, w, l)]
                    name = inverse.get(idx, AIR)
                    if is_air(name):
                        continue
                    yield x, y, z, name

    def summary(self) -> dict[str, Any]:
        used = sorted({name for _, _, _, name in self.iter_solid()})
        return {
            "format": "sponge_schematic",
            "schematic_version": self.version,
            "data_version": self.data_version,
            "kind": self.kind,
            "width": self.width,
            "height": self.height,
            "length": self.length,
            "offset": list(self.offset),
            "voxel_count": self.solid_count(),
            "palette": [AIR, *used] if used else [AIR],
            "biome": next(iter(self.biome_palette), DEFAULT_BIOME),
            "biome_count": len(self.biome_palette),
        }


def is_air(name: str) -> bool:
    base = block_type_name(name)
    return base in {"air", "cave_air", "void_air", "minecraft:air"} or base.endswith(":air")


def canonicalize_block(name: str) -> str:
    """正規化方塊狀態，保留 ``[property=value]``（Sponge Palette 鍵）。"""
    raw = (name or "").strip()
    if not raw:
        return AIR
    extra = ""
    base = raw
    if "[" in raw:
        base, rest = raw.split("[", 1)
        extra = "[" + rest
        base = base.strip()
    if ":" not in base:
        base = f"minecraft:{base}"
    namespace, _, path = base.partition(":")
    return f"{namespace.lower()}:{path.lower()}{extra}"


def block_type_name(name: str) -> str:
    return canonicalize_block(name).split("[", 1)[0]


def block_key(name: str) -> str:
    return block_type_name(name).split(":", 1)[-1]


def block_visual(name: str) -> dict[str, str | float]:
    visual = BLOCK_COLORS.get(block_key(name), {"color": "#8e8e93"})
    return {
        "color": str(visual.get("color") or "#8e8e93"),
        "opacity": float(visual.get("opacity", 1.0)),
        "emissive": str(visual.get("emissive") or "#000000"),
    }


def yzx_index(x: int, y: int, z: int, width: int, length: int) -> int:
    return (y * length + z) * width + x


def encode_varint(value: int) -> bytes:
    if value < 0:
        raise SchematicError("VarInt 不可為負")
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            break
    return bytes(out)


def decode_varints(data: bytes, count: int) -> list[int]:
    out: list[int] = []
    i = 0
    n = len(data)
    while len(out) < count and i < n:
        value = 0
        shift = 0
        while True:
            if i >= n:
                break
            byte = data[i]
            i += 1
            value |= (byte & 0x7F) << shift
            if not (byte & 0x80):
                out.append(value)
                break
            shift += 7
            if shift > 35:
                raise SchematicError("VarInt 過長")
        else:
            break
    if len(out) < count:
        out.extend([0] * (count - len(out)))
    return out[:count]


def encode_blockdata(indices: Iterable[int]) -> bytes:
    return b"".join(encode_varint(int(idx)) for idx in indices)


def schematics_dir() -> Path:
    path = data_dir() / "schematics"
    path.mkdir(parents=True, exist_ok=True)
    return path


def schematic_path(building_id: str) -> Path:
    safe = "".join(ch for ch in str(building_id) if ch.isalnum() or ch in {"-", "_"}) or "building"
    return schematics_dir() / f"{safe}.schem"


def remove_schematic_file(building_id: str) -> None:
    path = schematic_path(building_id)
    if path.exists():
        path.unlink()


def palette_for_style(style: str) -> dict[str, str]:
    return dict(STYLE_PALETTES.get(style) or DEFAULT_PALETTE)


def infer_kind(prompt: str) -> str:
    text = prompt or ""
    mapping = (
        ("bridge", ("桥", "橋", "bridge")),
        ("tower", ("塔", "tower", "瞭望")),
        ("temple", ("殿", "圣殿", "神殿", "temple")),
        ("house", ("屋", "房", "小屋", "house", "隐所")),
        ("garden", ("庭园", "庭園", "花园", "園", "garden")),
        ("harbor", ("港", "码头", "碼頭", "harbor", "帆")),
        ("colonnade", ("廊", "回廊", "colonnade")),
        ("workshop", ("工坊", "市集", "workshop")),
    )
    for kind, keys in mapping:
        if any(key in text for key in keys):
            return kind
    return "pavilion"


def generate_structure(
    *,
    prompt: str,
    style: str,
    block_count: int,
    seed: str = "",
    region: str = "",
    biome: str = "",
) -> Schematic:
    budget = max(16, min(int(block_count), MAX_BLOCKS))
    kind = infer_kind(prompt)
    rng = random.Random(_seed_int(f"{seed}|{prompt}|{style}|{kind}|{budget}"))
    width, height, length = _size_for(kind, budget, rng)
    grid = VoxelGrid(width, height, length)
    mats = palette_for_style(style)
    builders = {
        "bridge": _build_bridge,
        "tower": _build_tower,
        "temple": _build_temple,
        "house": _build_house,
        "garden": _build_garden,
        "harbor": _build_harbor,
        "colonnade": _build_colonnade,
        "workshop": _build_workshop,
        "pavilion": _build_pavilion,
    }
    builders.get(kind, _build_pavilion)(grid, mats, rng)
    if grid.solid_count() > budget:
        grid.trim_to(budget, rng)
    biome_id = (biome or REGION_BIOMES.get(region) or DEFAULT_BIOME).strip() or DEFAULT_BIOME
    if ":" not in biome_id:
        biome_id = f"minecraft:{biome_id}"
    schematic = grid.to_schematic(kind=kind, biome=biome_id)
    schematic.metadata = {
        "Name": (prompt or kind)[:80],
        "Author": "Linkin",
        "Date": ("long", int(time.time() * 1000)),
    }
    return schematic


def encode_schematic(schematic: Schematic, *, version: int | None = None) -> bytes:
    """寫出 Sponge Schematic。預設 v3；``version=2`` 可產出舊格式供相容測試。"""
    prepared = _ensure_air_palette(schematic)
    target = int(version if version is not None else (prepared.version or SPONGE_VERSION))
    if target >= 3:
        prepared.version = 3
        return _encode_v3(prepared)
    prepared.version = max(1, min(target, SPONGE_VERSION_V2))
    return _encode_v2(prepared)


_B64_DATA_URL = re.compile(r"^data:[^;]*;base64,", re.IGNORECASE)


def schematic_to_base64(schematic: Schematic, *, version: int | None = None) -> str:
    """Gzip .schem 的標準 Base64（不含換行）。"""
    raw = encode_schematic(schematic, version=version)
    return base64.b64encode(raw).decode("ascii")


def b64_to_schem_bytes(text: str) -> bytes:
    """把 Base64（可含空白或 data URL）還原成 Gzip .schem bytes。"""
    cleaned = "".join(str(text or "").split())
    cleaned = _B64_DATA_URL.sub("", cleaned)
    if not cleaned:
        raise SchematicError("空的 Base64 schematic")
    pad = (-len(cleaned)) % 4
    if pad:
        cleaned += "=" * pad
    try:
        raw = base64.b64decode(cleaned, validate=False)
    except Exception as exc:
        raise SchematicError("Base64 無法解碼") from exc
    if not raw:
        raise SchematicError("空的 schematic")
    if len(raw) > MAX_IMPORT_BYTES:
        raise SchematicError("schematic 檔案過大")
    return raw


def decode_schematic_base64(text: str) -> Schematic:
    return decode_schematic(b64_to_schem_bytes(text))


def build_small_house_schematic(
    *,
    name: str = "小型避難所",
    author: str = "靈境·Linkin",
    description: str = "簡單 3x3 建築（草皮地基、鵝卵石外牆、橡木內裝）",
) -> Schematic:
    """教學用 3×3×3 避難所，BlockData 為 YZX。"""
    width, height, length = 3, 3, 3
    cobble, planks, grass = "minecraft:cobblestone", "minecraft:oak_planks", "minecraft:grass_block"
    palette = {AIR: 0, cobble: 1, planks: 2, grass: 3}
    blocks: list[int] = []
    for y in range(height):
        for z in range(length):
            for x in range(width):
                if y == 0:
                    blocks.append(3)
                elif x in {0, width - 1} or z in {0, length - 1}:
                    blocks.append(1)
                else:
                    blocks.append(2)
    return Schematic(
        width=width,
        height=height,
        length=length,
        palette=palette,
        blocks=blocks,
        version=SPONGE_VERSION,
        data_version=DEFAULT_DATA_VERSION,
        metadata={
            "Name": name,
            "Author": author,
            "Description": description,
        },
        kind="house",
        biome_palette={DEFAULT_BIOME: 0},
        biomes=[0] * (width * height * length),
    )


def decode_schematic(data: bytes) -> Schematic:
    if not data:
        raise SchematicError("空的 schematic")
    if len(data) > MAX_IMPORT_BYTES:
        raise SchematicError("schematic 檔案過大")
    try:
        _name, root = nbt.loads_gzip(data)
    except nbt.NbtError as exc:
        raise SchematicError(str(exc)) from exc
    body = _unwrap_root(root)
    version = int(body.get("Version") or 1)
    if version < 1:
        raise SchematicError(f"不支援的 Schematic Version：{version}")
    data_version = int(body.get("DataVersion") or 0)
    width = int(body.get("Width") or 0) & 0xFFFF
    height = int(body.get("Height") or 0) & 0xFFFF
    length = int(body.get("Length") or 0) & 0xFFFF
    if min(width, height, length) <= 0:
        raise SchematicError("Width / Height / Length 必須為正")
    if max(width, height, length) > MAX_AXIS:
        raise SchematicError(f"單軸尺寸不得超過 {MAX_AXIS}")
    volume = width * height * length
    if volume > MAX_AXIS * MAX_AXIS * MAX_AXIS:
        raise SchematicError("結構體積過大")
    palette_raw, block_bytes, block_entities_raw = _blocks_payload(body)
    palette = _coerce_palette(palette_raw) if palette_raw else {AIR: 0}
    indices = decode_varints(block_bytes, volume) if block_bytes else [0] * volume
    offset_raw = body.get("Offset") or [0, 0, 0]
    if not isinstance(offset_raw, (list, tuple)) or len(offset_raw) < 3:
        offset = (0, 0, 0)
    else:
        offset = (int(offset_raw[0]), int(offset_raw[1]), int(offset_raw[2]))
    biome_palette, biomes = _decode_biomes(body, width, height, length)
    entities_raw = body.get("Entities") or []
    if not isinstance(entities_raw, list):
        entities_raw = []
    schematic = Schematic(
        width=width,
        height=height,
        length=length,
        palette=palette,
        blocks=indices,
        version=version,
        data_version=data_version,
        offset=offset,
        metadata=dict(body.get("Metadata") or {}) if isinstance(body.get("Metadata"), dict) else {},
        kind="imported",
        biome_palette=biome_palette,
        biomes=biomes,
        block_entities=[_normalize_block_entity(item) for item in block_entities_raw if isinstance(item, dict)],
        entities=[_normalize_entity(item) for item in entities_raw if isinstance(item, dict)],
    )
    if schematic.solid_count() > MAX_BLOCKS:
        raise SchematicError(f"實心方塊不得超過 {MAX_BLOCKS}")
    if schematic.solid_count() <= 0:
        raise SchematicError("schematic 沒有可見方塊")
    return schematic


def write_schematic_file(building_id: str, schematic: Schematic) -> Path:
    path = schematic_path(building_id)
    schematic.version = SPONGE_VERSION
    path.write_bytes(encode_schematic(schematic, version=SPONGE_VERSION))
    return path


def read_schematic_file(path: Path) -> Schematic:
    return decode_schematic(path.read_bytes())


def preview_payload(schematic: Schematic, *, building_id: str = "") -> dict[str, Any]:
    used: list[str] = []
    index_of: dict[str, int] = {}
    voxels: list[dict[str, int]] = []
    for x, y, z, name in schematic.iter_solid():
        if name not in index_of:
            index_of[name] = len(used)
            used.append(name)
        voxels.append({"x": x, "y": y, "z": z, "i": index_of[name]})
    palette = [{"name": name, **block_visual(name)} for name in used]
    return {
        "id": building_id,
        "kind": schematic.kind,
        "width": schematic.width,
        "height": schematic.height,
        "length": schematic.length,
        "version": schematic.version,
        "data_version": schematic.data_version,
        "voxel_count": len(voxels),
        "palette": palette,
        "voxels": voxels,
        "biome": next(iter(schematic.biome_palette), DEFAULT_BIOME),
        "schematic_base64": schematic_to_base64(schematic),
        "schematic_filename": f"{building_id or 'structure'}.schem",
    }


def attach_model(
    building: dict[str, Any],
    model: Schematic,
    *,
    generator: str = "procedural",
    design: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """把已生成的 Schematic 寫盤並將摘要併入建築紀錄。（本地定制，恢復自舊版）

    ``generator``：``"procedural"``（程序化）或 ``"llm"``（LLM 設計）；
    ``design`` 為 LLM 設計的 DSL payload（op 序列），僅 LLM 路徑附帶。
    """
    rec_id = str(building.get("id") or "building")
    write_schematic_file(rec_id, model)
    summary = model.summary()
    origin = "由 LLM 設計" if generator == "llm" else "生成"
    note = (
        f"已{origin} Sponge Schematic v{model.version}（{summary['voxel_count']} 方塊，"
        f"{summary['width']}×{summary['height']}×{summary['length']}）。"
    )
    record = {
        **building,
        **summary,
        "block_count": summary["voxel_count"],
        "block_budget": int(building.get("block_count") or summary["voxel_count"]),
        "schematic_file": schematic_path(rec_id).name,
        "generator": generator,
        "note": note,
    }
    if design is not None:
        record["design"] = design
    return record


def attach_schematic(building: dict[str, Any]) -> dict[str, Any]:
    rec_id = str(building.get("id") or "building")
    model = generate_structure(
        prompt=str(building.get("prompt") or ""),
        style=str(building.get("style") or ""),
        block_count=int(building.get("block_count") or 64),
        seed=rec_id,
        region=str(building.get("region") or ""),
    )
    write_schematic_file(rec_id, model)
    summary = model.summary()
    note = (
        f"已生成 Sponge Schematic v{model.version}（{summary['voxel_count']} 方塊，"
        f"{summary['width']}×{summary['height']}×{summary['length']}）。"
    )
    return {
        **building,
        **summary,
        "block_count": summary["voxel_count"],
        "block_budget": int(building.get("block_count") or summary["voxel_count"]),
        "schematic_file": schematic_path(rec_id).name,
        "note": note,
    }


def ensure_schematic(building: dict[str, Any]) -> tuple[dict[str, Any], Schematic]:
    rec_id = str(building.get("id") or "")
    path = schematic_path(rec_id)
    if path.exists():
        model = read_schematic_file(path)
        if building.get("format") == "sponge_schematic" and building.get("width"):
            model.kind = str(building.get("kind") or model.kind)
            return building, model
        updated = {**building, **model.summary(), "schematic_file": path.name}
        return updated, model
    updated = attach_schematic(building)
    return updated, read_schematic_file(schematic_path(rec_id))


def import_schematic_bytes(
    data: bytes,
    *,
    building_id: str,
    prompt: str = "",
    style: str = "",
    location: Any = "0, 64, 0",
    region: str = "",
) -> tuple[dict[str, Any], Schematic]:
    model = decode_schematic(data)
    model.version = SPONGE_VERSION
    write_schematic_file(building_id, model)
    summary = model.summary()
    record = {
        "id": building_id,
        "prompt": prompt or str(model.metadata.get("Name") or "imported schematic"),
        "style": style or "imported",
        "location": location,
        "region": region,
        "status": "planned",
        "note": f"已匯入 Sponge Schematic v{model.version}（{summary['voxel_count']} 方塊）。",
        **summary,
        "block_count": summary["voxel_count"],
        "schematic_file": schematic_path(building_id).name,
    }
    return record, model


def _unwrap_root(root: dict[str, Any]) -> dict[str, Any]:
    if "Version" in root and ("Width" in root or "Blocks" in root or "Palette" in root):
        return root
    nested = root.get("Schematic")
    if isinstance(nested, dict):
        return _unwrap_root(nested)
    raise SchematicError("不是 Sponge Schematic（缺少 Version）")


def _ensure_air_palette(schematic: Schematic) -> Schematic:
    palette = {canonicalize_block(name): int(idx) for name, idx in schematic.palette.items()}
    if AIR in palette:
        schematic.palette = palette
        return schematic
    shifted = {AIR: 0, **{name: idx + 1 for name, idx in palette.items()}}
    return Schematic(
        width=schematic.width,
        height=schematic.height,
        length=schematic.length,
        palette=shifted,
        blocks=[idx + 1 for idx in schematic.blocks],
        version=schematic.version,
        data_version=schematic.data_version,
        offset=schematic.offset,
        metadata=schematic.metadata,
        kind=schematic.kind,
        biome_palette=dict(schematic.biome_palette),
        biomes=list(schematic.biomes),
        block_entities=list(schematic.block_entities),
        entities=list(schematic.entities),
    )


def _typed_int_palette(palette: dict[str, int]) -> dict[str, Any]:
    return {str(name): ("int", int(idx)) for name, idx in palette.items()}


def _uniform_biomes(schematic: Schematic) -> tuple[dict[str, int], list[int]]:
    volume = schematic.volume()
    if schematic.biome_palette and len(schematic.biomes) == volume:
        return dict(schematic.biome_palette), list(schematic.biomes)
    biome = next(iter(schematic.biome_palette), DEFAULT_BIOME) if schematic.biome_palette else DEFAULT_BIOME
    return {biome: 0}, [0] * volume


def _encode_v3(schematic: Schematic) -> bytes:
    biome_palette, biomes = _uniform_biomes(schematic)
    payload: dict[str, Any] = {
        "Version": ("int", 3),
        "DataVersion": ("int", int(schematic.data_version or DEFAULT_DATA_VERSION)),
        "Width": ("short", int(schematic.width)),
        "Height": ("short", int(schematic.height)),
        "Length": ("short", int(schematic.length)),
        "Offset": ("int_array", [int(v) for v in schematic.offset]),
        "Blocks": {
            "Palette": _typed_int_palette(schematic.palette),
            "Data": ("byte_array", encode_blockdata(schematic.blocks)),
            "BlockEntities": nbt.NbtList(
                nbt.TAG_COMPOUND,
                [_encode_block_entity(item) for item in schematic.block_entities],
            ),
        },
        "Biomes": {
            "Palette": _typed_int_palette(biome_palette),
            "Data": ("byte_array", encode_blockdata(biomes)),
        },
        "Entities": nbt.NbtList(
            nbt.TAG_COMPOUND,
            [_encode_entity(item) for item in schematic.entities],
        ),
    }
    if schematic.metadata:
        payload["Metadata"] = schematic.metadata
    return nbtlib_dumps_gzip("", {"Schematic": payload})


def _encode_v2(schematic: Schematic) -> bytes:
    biome_palette, biomes_3d = _uniform_biomes(schematic)
    column = schematic.width * schematic.length
    biomes_2d = biomes_3d[:column]
    payload: dict[str, Any] = {
        "Version": ("int", 2),
        "DataVersion": ("int", int(schematic.data_version or DEFAULT_DATA_VERSION)),
        "Width": ("short", int(schematic.width)),
        "Height": ("short", int(schematic.height)),
        "Length": ("short", int(schematic.length)),
        "Offset": ("int_array", [int(v) for v in schematic.offset]),
        "PaletteMax": ("int", len(schematic.palette)),
        "Palette": _typed_int_palette(schematic.palette),
        "BlockData": ("byte_array", encode_blockdata(schematic.blocks)),
        "BlockEntities": nbt.NbtList(
            nbt.TAG_COMPOUND,
            [_encode_block_entity(item) for item in schematic.block_entities],
        ),
        "Entities": nbt.NbtList(
            nbt.TAG_COMPOUND,
            [_encode_entity(item) for item in schematic.entities],
        ),
        "BiomePalette": _typed_int_palette(biome_palette),
        "BiomeData": ("byte_array", encode_blockdata(biomes_2d)),
    }
    if schematic.metadata:
        payload["Metadata"] = schematic.metadata
    return nbtlib_dumps_gzip("Schematic", payload)


def _encode_block_entity(item: dict[str, Any]) -> dict[str, Any]:
    pos = item.get("Pos") or [item.get("x") or 0, item.get("y") or 0, item.get("z") or 0]
    data = item.get("Data") if isinstance(item.get("Data"), dict) else {}
    extra = {k: v for k, v in item.items() if k not in {"Pos", "Id", "Data", "x", "y", "z"}}
    return {
        "Pos": ("int_array", [int(v) for v in list(pos)[:3]]),
        "Id": str(item.get("Id") or item.get("id") or "minecraft:air"),
        "Data": {**extra, **data},
    }


def _encode_entity(item: dict[str, Any]) -> dict[str, Any]:
    pos = item.get("Pos") or [0.0, 0.0, 0.0]
    data = item.get("Data") if isinstance(item.get("Data"), dict) else {}
    extra = {k: v for k, v in item.items() if k not in {"Pos", "Id", "Data"}}
    coords = [float(v) for v in list(pos)[:3]]
    while len(coords) < 3:
        coords.append(0.0)
    return {
        "Pos": nbt.NbtList(nbt.TAG_DOUBLE, coords),
        "Id": str(item.get("Id") or item.get("id") or "minecraft:pig"),
        "Data": {**extra, **data},
    }


def _blocks_payload(body: dict[str, Any]) -> tuple[dict[str, Any], bytes, list[Any]]:
    container = body.get("Blocks") if isinstance(body.get("Blocks"), dict) else None
    if isinstance(container, dict):
        palette = container.get("Palette") or container.get("BlockPalette") or {}
        raw = container.get("Data") or container.get("BlockData") or b""
        entities = container.get("BlockEntities") or []
        return palette, bytes(raw), list(entities) if isinstance(entities, list) else []
    palette = body.get("Palette") or body.get("BlockPalette") or {}
    raw = body.get("BlockData") or body.get("Data") or b""
    entities = body.get("BlockEntities") or []
    return palette, bytes(raw), list(entities) if isinstance(entities, list) else []


def _decode_biomes(
    body: dict[str, Any],
    width: int,
    height: int,
    length: int,
) -> tuple[dict[str, int], list[int]]:
    volume = width * height * length
    column = width * length
    container = body.get("Biomes")
    palette_raw: Any = {}
    raw = b""
    if isinstance(container, dict):
        palette_raw = container.get("Palette") or container.get("BiomePalette") or {}
        raw = bytes(container.get("Data") or container.get("BiomeData") or b"")
    elif body.get("BiomePalette") or body.get("BiomeData"):
        palette_raw = body.get("BiomePalette") or {}
        raw = bytes(body.get("BiomeData") or b"")
    if not raw:
        return {DEFAULT_BIOME: 0}, [0] * volume
    varint_count = sum(1 for byte in raw if (byte & 0x80) == 0)
    if varint_count == column and column != volume:
        layer = decode_varints(raw, column)
        biomes = layer * height
    else:
        biomes = decode_varints(raw, volume)
    palette = _coerce_biome_palette(palette_raw) if palette_raw else {DEFAULT_BIOME: 0}
    if not palette:
        palette = {DEFAULT_BIOME: 0}
    if len(biomes) < volume:
        biomes.extend([0] * (volume - len(biomes)))
    return palette, biomes[:volume]


def _coerce_palette(raw: Any) -> dict[str, int]:
    if not isinstance(raw, dict):
        raise SchematicError("Palette 必須為 compound")
    out: dict[str, int] = {}
    for name, idx in raw.items():
        out[canonicalize_block(str(name))] = int(idx)
    return out


def _coerce_biome_palette(raw: Any) -> dict[str, int]:
    if not isinstance(raw, dict):
        return {DEFAULT_BIOME: 0}
    out: dict[str, int] = {}
    for name, idx in raw.items():
        key = str(name).strip() or DEFAULT_BIOME
        if ":" not in key:
            key = f"minecraft:{key}"
        out[key] = int(idx)
    return out


def _normalize_block_entity(raw: dict[str, Any]) -> dict[str, Any]:
    if "Pos" in raw and isinstance(raw.get("Pos"), (list, tuple)):
        pos = [int(v) for v in list(raw["Pos"])[:3]]
        data = raw.get("Data") if isinstance(raw.get("Data"), dict) else {}
        extra = {k: v for k, v in raw.items() if k not in {"Pos", "Id", "Data"}}
        return {"Pos": pos, "Id": str(raw.get("Id") or ""), "Data": {**extra, **data}}
    pos = [int(raw.get("x") or 0), int(raw.get("y") or 0), int(raw.get("z") or 0)]
    extra = {k: v for k, v in raw.items() if k not in {"x", "y", "z", "Id"}}
    return {"Pos": pos, "Id": str(raw.get("Id") or ""), "Data": extra}


def _normalize_entity(raw: dict[str, Any]) -> dict[str, Any]:
    pos_raw = raw.get("Pos") or [0.0, 0.0, 0.0]
    coords = [float(v) for v in list(pos_raw)[:3]]
    while len(coords) < 3:
        coords.append(0.0)
    data = raw.get("Data") if isinstance(raw.get("Data"), dict) else {}
    extra = {k: v for k, v in raw.items() if k not in {"Pos", "Id", "Data"}}
    return {"Pos": coords, "Id": str(raw.get("Id") or raw.get("id") or ""), "Data": {**extra, **data}}


def _seed_int(text: str) -> int:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _size_for(kind: str, budget: int, rng: random.Random) -> tuple[int, int, int]:
    budget = max(16, budget)
    if kind == "bridge":
        length = max(10, min(40, int(budget**0.48) + 8))
        width = 5 if budget < 280 else 7
        height = 6 if budget < 500 else 8
    elif kind == "tower":
        width = max(5, min(11, 5 + budget // 500))
        length = width
        height = max(8, min(24, budget // max(width * width, 1) + 8))
    elif kind == "temple":
        width = max(7, min(17, int(budget**0.38) + 5))
        length = width + rng.randint(0, 2)
        height = max(6, min(12, 5 + budget // 350))
    elif kind == "garden":
        width = max(7, min(18, int(budget**0.40) + 5))
        length = width + rng.randint(0, 3)
        height = 5
    elif kind == "harbor":
        length = max(10, min(22, int(budget**0.42) + 6))
        width = max(6, min(12, 6 + budget // 400))
        height = 6
    elif kind == "colonnade":
        length = max(10, min(24, int(budget**0.45) + 8))
        width = 5
        height = 6
    elif kind == "workshop":
        width = max(7, min(14, int(budget**0.36) + 6))
        length = width + 2
        height = 6
    else:
        width = max(6, min(13, int(budget**0.36) + 5))
        length = width + rng.randint(0, 2)
        height = max(5, min(9, 5 + budget // 450))
    while width * height * length < min(budget, 400) and width < 24:
        if width <= length:
            width += 1
        else:
            length += 1
    return width, height, length


class VoxelGrid:
    def __init__(self, width: int, height: int, length: int):
        self.width = width
        self.height = height
        self.length = length
        self.cells: dict[tuple[int, int, int], str] = {}

    def in_bounds(self, x: int, y: int, z: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height and 0 <= z < self.length

    def set(self, x: int, y: int, z: int, block: str) -> None:
        if not self.in_bounds(x, y, z):
            return
        name = canonicalize_block(block)
        if is_air(name):
            self.cells.pop((x, y, z), None)
        else:
            self.cells[(x, y, z)] = name

    def fill(self, x1: int, y1: int, z1: int, x2: int, y2: int, z2: int, block: str) -> None:
        xa, xb = sorted((x1, x2))
        ya, yb = sorted((y1, y2))
        za, zb = sorted((z1, z2))
        for y in range(ya, yb + 1):
            for z in range(za, zb + 1):
                for x in range(xa, xb + 1):
                    self.set(x, y, z, block)

    def solid_count(self) -> int:
        return len(self.cells)

    def trim_to(self, budget: int, rng: random.Random) -> None:
        extra = list(self.cells.keys())
        rng.shuffle(extra)
        for key in extra[budget:]:
            self.cells.pop(key, None)

    def to_schematic(self, *, kind: str, biome: str = DEFAULT_BIOME) -> Schematic:
        palette: dict[str, int] = {AIR: 0}
        for name in sorted({canonicalize_block(v) for v in self.cells.values()}):
            if name not in palette:
                palette[name] = len(palette)
        volume = self.width * self.height * self.length
        blocks = [0] * volume
        for (x, y, z), name in self.cells.items():
            blocks[yzx_index(x, y, z, self.width, self.length)] = palette[name]
        biome_id = biome if ":" in biome else f"minecraft:{biome}"
        return Schematic(
            width=self.width,
            height=self.height,
            length=self.length,
            palette=palette,
            blocks=blocks,
            kind=kind,
            version=SPONGE_VERSION,
            biome_palette={biome_id: 0},
            biomes=[0] * volume,
        )


def _build_house(grid: VoxelGrid, mats: dict[str, str], rng: random.Random) -> None:
    w, h, l = grid.width, grid.height, grid.length
    wall_top = max(2, h - 3)
    grid.fill(0, 0, 0, w - 1, 0, l - 1, mats["floor"])
    for y in range(1, wall_top + 1):
        for x in range(w):
            grid.set(x, y, 0, mats["primary"])
            grid.set(x, y, l - 1, mats["primary"])
        for z in range(l):
            grid.set(0, y, z, mats["primary"])
            grid.set(w - 1, y, z, mats["primary"])
        grid.set(0, y, 0, mats["secondary"])
        grid.set(w - 1, y, 0, mats["secondary"])
        grid.set(0, y, l - 1, mats["secondary"])
        grid.set(w - 1, y, l - 1, mats["secondary"])
    door_x = w // 2
    grid.set(door_x, 1, 0, AIR)
    grid.set(door_x, 2, 0, AIR)
    if w > 4:
        grid.set(1, 2, 0, AIR)
        grid.set(w - 2, 2, 0, AIR)
    roof_y = wall_top + 1
    for step in range(max(2, w // 2 + 1)):
        y = min(h - 1, roof_y + step // 2)
        x1, x2 = step, w - 1 - step
        if x1 > x2:
            break
        grid.fill(x1, y, 0, x2, y, l - 1, mats["roof"])
    grid.set(1, wall_top, 1, mats["accent"])
    grid.set(w - 2, wall_top, l - 2, mats["accent"])
    if rng.random() > 0.4:
        grid.fill(w - 2, wall_top, l // 2, w - 2, h - 1, l // 2, mats["secondary"])


def _build_bridge(grid: VoxelGrid, mats: dict[str, str], rng: random.Random) -> None:
    w, h, l = grid.width, grid.height, grid.length
    deck_y = min(h - 2, max(2, h // 2))
    pier_z = max(1, l // 6)
    grid.fill(1, 0, pier_z, w - 2, deck_y - 1, pier_z + 1, mats["secondary"])
    grid.fill(1, 0, l - pier_z - 2, w - 2, deck_y - 1, l - pier_z - 1, mats["secondary"])
    grid.fill(0, deck_y, 0, w - 1, deck_y, l - 1, mats["primary"])
    for z in range(l):
        grid.set(0, deck_y + 1, z, mats["trim"])
        grid.set(w - 1, deck_y + 1, z, mats["trim"])
        if z % 3 == 0:
            grid.set(0, deck_y + 2, z, mats["accent"])
            grid.set(w - 1, deck_y + 2, z, mats["accent"])
    if rng.random() > 0.5:
        mid = l // 2
        grid.fill(1, 1, mid, w - 2, deck_y - 1, mid, mats["secondary"])


def _build_tower(grid: VoxelGrid, mats: dict[str, str], rng: random.Random) -> None:
    w, h, l = grid.width, grid.height, grid.length
    grid.fill(0, 0, 0, w - 1, 0, l - 1, mats["floor"])
    for y in range(1, h - 1):
        for x in range(w):
            grid.set(x, y, 0, mats["primary"])
            grid.set(x, y, l - 1, mats["primary"])
        for z in range(l):
            grid.set(0, y, z, mats["primary"])
            grid.set(w - 1, y, z, mats["primary"])
        grid.set(0, y, 0, mats["secondary"])
        grid.set(w - 1, y, 0, mats["secondary"])
        grid.set(0, y, l - 1, mats["secondary"])
        grid.set(w - 1, y, l - 1, mats["secondary"])
        if y % 3 == 2:
            grid.set(w // 2, y, 0, AIR)
    grid.set(w // 2, 1, 0, AIR)
    grid.set(w // 2, 2, 0, AIR)
    battlement = h - 1
    for x in range(w):
        for z in range(l):
            if x in {0, w - 1} or z in {0, l - 1}:
                if (x + z + rng.randint(0, 1)) % 2 == 0:
                    grid.set(x, battlement, z, mats["trim"])
    grid.set(1, h - 2, 1, mats["accent"])


def _build_temple(grid: VoxelGrid, mats: dict[str, str], rng: random.Random) -> None:
    w, h, l = grid.width, grid.height, grid.length
    steps = min(3, h - 3)
    for i in range(steps):
        grid.fill(i, i, i, w - 1 - i, i, l - 1 - i, mats["floor"] if i == 0 else mats["primary"])
    col_y1, col_y2 = steps, min(h - 2, steps + 3)
    for x, z in ((steps, steps), (w - 1 - steps, steps), (steps, l - 1 - steps), (w - 1 - steps, l - 1 - steps)):
        grid.fill(x, col_y1, z, x, col_y2, z, mats["secondary"])
        grid.set(x, col_y2 + 0 if col_y2 < h else h - 1, z, mats["accent"])
    roof = min(h - 1, col_y2 + 1)
    grid.fill(steps - 1, roof, steps - 1, w - steps, roof, l - steps, mats["roof"])
    grid.fill(w // 2 - 1, steps, l // 2 - 1, w // 2 + 1, steps, l // 2 + 1, mats["trim"])
    if rng.random() > 0.3:
        grid.set(w // 2, steps + 1, l // 2, mats["accent"])


def _build_garden(grid: VoxelGrid, mats: dict[str, str], rng: random.Random) -> None:
    w, h, l = grid.width, grid.height, grid.length
    grid.fill(0, 0, 0, w - 1, 0, l - 1, mats["floor"])
    for x in range(w):
        grid.set(x, 1, 0, mats["fill"])
        grid.set(x, 1, l - 1, mats["fill"])
    for z in range(l):
        grid.set(0, 1, z, mats["fill"])
        grid.set(w - 1, 1, z, mats["fill"])
    grid.fill(w // 2, 0, 1, w // 2, 0, l - 2, mats["trim"])
    pond_x1, pond_x2 = max(2, w // 2 - 1), min(w - 3, w // 2 + 1)
    pond_z1, pond_z2 = max(2, l // 2 - 1), min(l - 3, l // 2 + 1)
    grid.fill(pond_x1, 0, pond_z1, pond_x2, 0, pond_z2, "minecraft:water")
    for _ in range(max(3, w // 2)):
        grid.set(rng.randint(1, w - 2), 1, rng.randint(1, l - 2), mats["accent"] if rng.random() > 0.6 else mats["primary"])
    grid.set(1, 2, 1, mats["accent"])
    grid.set(w - 2, 2, l - 2, mats["accent"])
    if h > 3:
        grid.fill(1, 3, 1, 1, min(h - 1, 4), 1, mats["secondary"])


def _build_harbor(grid: VoxelGrid, mats: dict[str, str], rng: random.Random) -> None:
    w, h, l = grid.width, grid.height, grid.length
    grid.fill(0, 0, 0, w - 1, 0, l - 1, "minecraft:water")
    dock_z = max(2, l // 3)
    grid.fill(1, 1, 0, w - 2, 1, dock_z, mats["primary"])
    for x in (1, w - 2):
        grid.fill(x, 2, 1, x, min(h - 1, 4), 1, mats["secondary"])
        grid.set(x, min(h - 1, 4), 1, mats["accent"])
    grid.fill(2, 2, 2, min(w - 3, 4), 2, min(dock_z - 1, 4), mats["fill"])
    if rng.random() > 0.4:
        grid.fill(w // 2, 1, dock_z, w // 2, 1, l - 2, mats["primary"])


def _build_colonnade(grid: VoxelGrid, mats: dict[str, str], rng: random.Random) -> None:
    w, h, l = grid.width, grid.height, grid.length
    grid.fill(0, 0, 0, w - 1, 0, l - 1, mats["floor"])
    beam_y = min(h - 2, 4)
    for z in range(1, l - 1, 2):
        grid.fill(1, 1, z, 1, beam_y, z, mats["secondary"])
        grid.fill(w - 2, 1, z, w - 2, beam_y, z, mats["secondary"])
        if rng.random() > 0.5:
            grid.set(1, beam_y, z, mats["accent"])
    grid.fill(0, beam_y, 0, w - 1, beam_y, l - 1, mats["roof"])
    grid.fill(0, beam_y + 1, 0, w - 1, min(h - 1, beam_y + 1), l - 1, mats["trim"])


def _build_workshop(grid: VoxelGrid, mats: dict[str, str], rng: random.Random) -> None:
    _build_house(grid, mats, rng)
    w, l = grid.width, grid.length
    grid.fill(2, 1, 2, min(w - 3, 4), 1, min(l - 3, 4), mats["fill"])
    grid.set(2, 2, 2, mats["accent"])


def _build_pavilion(grid: VoxelGrid, mats: dict[str, str], rng: random.Random) -> None:
    w, h, l = grid.width, grid.height, grid.length
    grid.fill(0, 0, 0, w - 1, 0, l - 1, mats["floor"])
    posts = ((1, 1), (w - 2, 1), (1, l - 2), (w - 2, l - 2))
    cap = min(h - 2, 4)
    for x, z in posts:
        grid.fill(x, 1, z, x, cap, z, mats["secondary"])
    for z in range(1, l - 1):
        grid.set(0, 1, z, mats["trim"])
        grid.set(w - 1, 1, z, mats["trim"])
    roof = cap + 1
    if roof < h:
        grid.fill(0, roof, 0, w - 1, roof, l - 1, mats["roof"])
        if roof + 1 < h:
            grid.fill(1, roof + 1, 1, w - 2, roof + 1, l - 2, mats["roof"])
    grid.set(w // 2, cap, l // 2, mats["accent"])
    if rng.random() > 0.5:
        grid.set(w // 2, 1, l // 2, mats["fill"])
