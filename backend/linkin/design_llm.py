"""LLM 建築設計層：把自然語言需求翻譯成受約束的建築 DSL，再編譯為體素模型。

流程：
    使用者 prompt + 風格 / 區域 / 方塊預算
        ▼
    call_llm（DESIGN_SYSTEM_PROMPT 描述 DSL 與輸出 JSON 格式）
        ▼
    parse_design（嚴格校驗：op 白名單、尺寸、材質白名單、op 數量）
        ▼
    compile_design（op 順序執行 → VoxelGrid → 預算裁剪）
        ▼
    Schematic（與程序化生成器同一規格，Sponge v3）

任一環節失敗都回傳 None，由呼叫方（api.generate_building）自動降級到
程序化生成器 generate_structure —— 與本倉庫「LLM + 規則 fallback」的
一致哲學（評估引擎、NPC 對話、任務生成皆同）。

LLM 一律經 backend.core.llm.call_llm（AGENTS.md 約束 #1）；
測試以 monkeypatch 隔離，無需真實 API 金鑰。

DSL op 目錄（皆需 material；y=0 為地面；後面的 op 覆蓋前面的）：
- cuboid  x,y,z,w,h,d[,hollow]        實心／僅外殼的長方體
- line    x1,y1,z1,x2,y2,z2           直線（橋面、樑、柱）
- column  x,y,z,height[,radius]       垂直圓柱（燈柱、塔柱）
- arch    x,y,z,span,height[,axis]    半圓拱（拱形橋體），axis=x|z
- pyramid x,y,z,w,d,height            階梯金字塔（神殿頂）
- gable   x,y,z,w,d,height            人字屋頂（脊沿 x）

material 可用風格調色盤角色名（primary/secondary/accent/roof/floor/trim/fill）
或方塊白名單（BLOCK_COLORS ∪ 各風格調色盤），air 用於鏤空門窗。
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import random
import re
import time
from dataclasses import dataclass, field
from typing import Any

from backend.core.llm import call_llm
from backend.core.stage_router import resolve_stage_model
from backend.linkin.schematic import (
    AIR,
    BLOCK_COLORS,
    DEFAULT_BIOME,
    MAX_AXIS,
    REGION_BIOMES,
    STYLE_PALETTES,
    Schematic,
    VoxelGrid,
    block_key,
    canonicalize_block,
    infer_kind,
    is_air,
    palette_for_style,
)
from backend.linkin.tools import MAX_BLOCKS

logger = logging.getLogger(__name__)


def _seed_int(text: str) -> int:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")

# ── 設計護欄常量 ──
MAX_OPS = 48                 # 單個設計的 op 數量上限
MAX_DESIGN_AXIS = 64         # 畫布單軸上限（小於 MAX_AXIS，控制體積）
MAX_DESIGN_VOLUME = 65_536   # 畫布體積上限（to_schematic 會分配 w*h*l）
MAX_OP_VOLUME = 65_536       # 單 op 影響格數上限
MAX_LINE_STEPS = 512         # line op 迭代上限
MAX_COLUMN_RADIUS = 4
KNOWN_KINDS = frozenset(
    {"bridge", "tower", "temple", "house", "garden", "harbor", "colonnade", "workshop", "pavilion"}
)

_TRUE = {"1", "true", "yes", "on"}

DESIGN_SYSTEM_PROMPT = (
    "你是靈境的首席建築師，擅長把自然語言建築需求翻譯成體素建造序列。"
    "你只輸出一個符合使用者訊息中 JSON 格式說明的 JSON 物件，"
    "不加任何解釋、散文或 Markdown 代碼柵欄。"
    "設計必須逐項回應需求中的每個具體要求（例如要求燈柱就必須建燈柱，"
    "要求拱形橋體就必須使用 arch op）。"
)

_DESIGN_EXAMPLE = {
    "kind": "house",
    "size": [9, 8, 9],
    "ops": [
        {"op": "cuboid", "x": 0, "y": 0, "z": 0, "w": 9, "h": 1, "d": 9, "material": "floor"},
        {"op": "cuboid", "x": 0, "y": 1, "z": 0, "w": 9, "h": 4, "d": 9, "material": "primary", "hollow": True},
        {"op": "cuboid", "x": 4, "y": 1, "z": 0, "w": 1, "h": 2, "d": 1, "material": "air"},
        {"op": "gable", "x": 0, "y": 5, "z": 0, "w": 9, "d": 9, "height": 4, "material": "roof"},
        {"op": "column", "x": 1, "y": 1, "z": 8, "height": 3, "material": "trim"},
        {"op": "cuboid", "x": 1, "y": 4, "z": 8, "w": 1, "h": 1, "d": 1, "material": "accent"},
    ],
}


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in _TRUE


def design_enabled() -> bool:
    """LLM 建築設計開關（EVOL_LINKIN_LLM_DESIGN，預設開啟）。"""
    return _env_flag("EVOL_LINKIN_LLM_DESIGN", True)


def _llm_ready() -> bool:
    """與 api._llm_ready 同邏輯：無金鑰或明確關閉時回 False（走程序化 fallback）。"""
    if _env_flag("EVOL_LINKIN_NO_LLM", False):
        return False
    try:
        from backend.core.llm_config import get_runtime_config

        cfg = get_runtime_config()
        key = str(cfg.get("api_key") or os.getenv("OPENAI_API_KEY") or "").strip()
    except Exception:  # noqa: BLE001 — 配置層不可用時退回環境變數
        key = str(os.getenv("OPENAI_API_KEY") or "").strip()
    return bool(key) and not key.startswith("sk-your")


def _allowed_material_keys() -> set[str]:
    """方塊白名單（block_key 形式）：視覺色表 ∪ 所有風格調色盤。"""
    keys = set(BLOCK_COLORS.keys())
    for palette in STYLE_PALETTES.values():
        for block in palette.values():
            keys.add(block_key(block))
    return keys


_ALLOWED_MATERIALS = _allowed_material_keys()


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """從 LLM 輸出抽取 JSON 物件（容忍代碼柵欄與前後雜訊）。"""
    raw = (text or "").strip()
    if not raw:
        return None
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", raw)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None


def _int(value: Any, *, lo: int, hi: int, default: int | None = None) -> int | None:
    """寬容整數解析並 clamp 到 [lo, hi]；無法解析回 default。"""
    try:
        num = int(float(value))
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, num))


def _resolve_material(raw: Any, mats: dict[str, str]) -> str | None:
    """角色名 → 調色盤方塊；白名單方塊 → 正規化名；其餘 → None（非法）。"""
    text = str(raw or "").strip()
    if not text:
        return None
    if text in mats:
        return canonicalize_block(mats[text])
    canonical = canonicalize_block(text)
    if is_air(canonical):
        return AIR
    if block_key(canonical) in _ALLOWED_MATERIALS:
        return canonical
    return None


@dataclass
class Design:
    """已校驗的 LLM 建築設計。"""

    kind: str
    width: int
    height: int
    length: int
    ops: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "size": [self.width, self.height, self.length],
            "ops": self.ops,
            "op_count": len(self.ops),
            "warnings": self.warnings[:20],
        }


# ── op 校驗 ──

_OP_SPECS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    # op 名 → (必填整數欄位, 選填整數欄位)
    "cuboid": (("x", "y", "z", "w", "h", "d"), ()),
    "line": (("x1", "y1", "z1", "x2", "y2", "z2"), ()),
    "column": (("x", "y", "z", "height"), ("radius",)),
    "arch": (("x", "y", "z", "span", "height"), ()),
    "pyramid": (("x", "y", "z", "w", "d", "height"), ()),
    "gable": (("x", "y", "z", "w", "d", "height"), ()),
}

_COORD_RANGE = (-MAX_DESIGN_AXIS, MAX_DESIGN_AXIS * 4)


def _validate_op(op: Any, mats: dict[str, str], warnings: list[str]) -> dict[str, Any] | None:
    """校驗並正規化單一 op；非法回 None 並記入 warnings。"""
    if not isinstance(op, dict):
        warnings.append("op 非物件，已跳過")
        return None
    name = str(op.get("op") or "").strip().lower()
    if name not in _OP_SPECS:
        warnings.append(f"未知 op：{name or '(空)'}，已跳過")
        return None
    required, optional = _OP_SPECS[name]
    clean: dict[str, Any] = {"op": name}
    lo, hi = _COORD_RANGE
    for key in required:
        if key in {"w", "h", "d", "height", "span"}:
            value = _int(op.get(key), lo=1, hi=MAX_DESIGN_AXIS)
        else:
            value = _int(op.get(key), lo=lo, hi=hi)
        if value is None:
            warnings.append(f"{name} 缺少或非法欄位 {key}，已跳過")
            return None
        clean[key] = value
    for key in optional:
        value = _int(op.get(key), lo=0, hi=MAX_COLUMN_RADIUS, default=0)
        clean[key] = value or 0
    material = _resolve_material(op.get("material"), mats)
    if material is None:
        warnings.append(f"{name} 材質非法（{op.get('material')!r}），已跳過")
        return None
    clean["material"] = material

    # 幾何護欄
    if name == "cuboid":
        volume = clean["w"] * clean["h"] * clean["d"]
        if volume > MAX_OP_VOLUME:
            warnings.append(f"cuboid 體積 {volume} 超過單 op 上限，已跳過")
            return None
        clean["hollow"] = bool(op.get("hollow"))
    elif name == "line":
        steps = max(
            abs(clean["x2"] - clean["x1"]),
            abs(clean["y2"] - clean["y1"]),
            abs(clean["z2"] - clean["z1"]),
        )
        if steps > MAX_LINE_STEPS:
            warnings.append(f"line 過長（{steps} 步），已跳過")
            return None
    elif name == "column":
        clean["height"] = max(1, min(clean["height"], MAX_DESIGN_AXIS))
    elif name == "arch":
        if clean["span"] < 2:
            warnings.append("arch span 至少為 2，已跳過")
            return None
        axis = str(op.get("axis") or "x").strip().lower()
        clean["axis"] = "z" if axis == "z" else "x"
    elif name in {"pyramid", "gable"}:
        clean["height"] = max(1, min(clean["height"], MAX_DESIGN_AXIS))
    return clean


def parse_design(text: str, *, style: str, prompt: str = "") -> Design | None:
    """解析並嚴格校驗 LLM 輸出的設計 JSON；無法使用時回 None（觸發 fallback）。"""
    data = _extract_json_object(text)
    if data is None:
        return None
    mats = palette_for_style(style)
    warnings: list[str] = []

    # 畫布尺寸：[w, h, d]（必要；缺 size 時由 ops 包圍盒推導）
    raw_size = data.get("size")
    if isinstance(raw_size, dict):
        raw_size = [raw_size.get(k) for k in ("w", "h", "d")]
    if isinstance(raw_size, (list, tuple)) and len(raw_size) >= 3:
        width = _int(raw_size[0], lo=1, hi=min(MAX_AXIS, MAX_DESIGN_AXIS))
        height = _int(raw_size[1], lo=1, hi=min(MAX_AXIS, MAX_DESIGN_AXIS))
        length = _int(raw_size[2], lo=1, hi=min(MAX_AXIS, MAX_DESIGN_AXIS))
    else:
        width = height = length = None
    if width is None or height is None or length is None:
        warnings.append("size 缺失或非法，將由 ops 包圍盒推導")

    raw_ops = data.get("ops")
    if not isinstance(raw_ops, list) or not raw_ops:
        return None
    if len(raw_ops) > MAX_OPS:
        warnings.append(f"ops 超過 {MAX_OPS} 個，截斷")
        raw_ops = raw_ops[:MAX_OPS]
    ops: list[dict[str, Any]] = []
    for op in raw_ops:
        clean = _validate_op(op, mats, warnings)
        if clean is not None:
            ops.append(clean)
    if not ops:
        return None

    if width is None or height is None or length is None:
        width, height, length = _bounding_size(ops)
    if width is None or height is None or length is None:
        return None
    if width * height * length > MAX_DESIGN_VOLUME:
        warnings.append(
            f"畫布體積 {width * height * length} 超過 {MAX_DESIGN_VOLUME}，已縮小高度"
        )
        while width * height * length > MAX_DESIGN_VOLUME and height > 1:
            height -= 1

    kind = str(data.get("kind") or "").strip().lower()
    if kind not in KNOWN_KINDS:
        kind = infer_kind(prompt)
    return Design(kind=kind, width=width, height=height, length=length, ops=ops, warnings=warnings)


def _bounding_size(ops: list[dict[str, Any]]) -> tuple[int | None, int | None, int | None]:
    """由 ops 座標推導畫布尺寸（clamp 到設計上限）。"""
    max_x = max_y = max_z = 0
    for op in ops:
        name = op["op"]
        if name == "line":
            pts = [(op["x1"], op["y1"], op["z1"]), (op["x2"], op["y2"], op["z2"])]
        elif name == "column":
            radius = int(op.get("radius") or 0)
            pts = [(op["x"] + radius, op["y"] + op["height"] - 1, op["z"] + radius)]
        elif name == "arch":
            if op.get("axis") == "z":
                pts = [(op["x"], op["y"] + op["height"], op["z"] + op["span"] - 1)]
            else:
                pts = [(op["x"] + op["span"] - 1, op["y"] + op["height"], op["z"])]
        elif name in {"pyramid", "gable"}:
            pts = [(op["x"] + op["w"] - 1, op["y"] + op["height"] - 1, op["z"] + op["d"] - 1)]
        else:  # cuboid
            pts = [(op["x"] + op["w"] - 1, op["y"] + op["h"] - 1, op["z"] + op["d"] - 1)]
        for px, py, pz in pts:
            max_x = max(max_x, int(px))
            max_y = max(max_y, int(py))
            max_z = max(max_z, int(pz))
    width = max(1, min(max_x + 1, MAX_DESIGN_AXIS))
    height = max(1, min(max_y + 1, MAX_DESIGN_AXIS))
    length = max(1, min(max_z + 1, MAX_DESIGN_AXIS))
    if width * height * length > MAX_DESIGN_VOLUME:
        return None, None, None
    return width, height, length


# ── op 執行（編譯到 VoxelGrid）──


def _exec_op(grid: VoxelGrid, op: dict[str, Any]) -> None:
    name = op["op"]
    mat = op["material"]
    if name == "cuboid":
        x, y, z, w, h, d = op["x"], op["y"], op["z"], op["w"], op["h"], op["d"]
        if op.get("hollow") and w > 2 and h > 2 and d > 2:
            for yy in range(h):
                for zz in range(d):
                    for xx in range(w):
                        if xx in (0, w - 1) or yy in (0, h - 1) or zz in (0, d - 1):
                            grid.set(x + xx, y + yy, z + zz, mat)
        else:
            grid.fill(x, y, z, x + w - 1, y + h - 1, z + d - 1, mat)
    elif name == "line":
        x1, y1, z1 = op["x1"], op["y1"], op["z1"]
        dx = op["x2"] - x1
        dy = op["y2"] - y1
        dz = op["z2"] - z1
        steps = max(abs(dx), abs(dy), abs(dz))
        if steps == 0:
            grid.set(x1, y1, z1, mat)
            return
        for i in range(steps + 1):
            t = i / steps
            grid.set(round(x1 + dx * t), round(y1 + dy * t), round(z1 + dz * t), mat)
    elif name == "column":
        x, y, z, height = op["x"], op["y"], op["z"], op["height"]
        radius = int(op.get("radius") or 0)
        for dy in range(height):
            if radius <= 0:
                grid.set(x, y + dy, z, mat)
            else:
                for dx in range(-radius, radius + 1):
                    for dz in range(-radius, radius + 1):
                        if dx * dx + dz * dz <= radius * radius:
                            grid.set(x + dx, y + dy, z + dz, mat)
    elif name == "arch":
        x, y, z, span, height = op["x"], op["y"], op["z"], op["span"], op["height"]
        for i in range(span):
            dy = round(height * math.sin(math.pi * i / (span - 1)))
            if op.get("axis") == "z":
                grid.set(x, y + dy, z + i, mat)
            else:
                grid.set(x + i, y + dy, z, mat)
    elif name == "pyramid":
        x, y, z, w, d, height = op["x"], op["y"], op["z"], op["w"], op["d"], op["height"]
        for k in range(height):
            wk, dk = w - 2 * k, d - 2 * k
            if wk < 1 or dk < 1:
                break
            grid.fill(x + k, y + k, z + k, x + k + wk - 1, y + k, z + k + dk - 1, mat)
    elif name == "gable":
        x, y, z, w, d, height = op["x"], op["y"], op["z"], op["w"], op["d"], op["height"]
        for k in range(height):
            z0, z1 = z + k, z + d - 1 - k
            if z0 > z1:
                break
            grid.fill(x, y + k, z0, x + w - 1, y + k, z1, mat)


def compile_design(
    design: Design,
    *,
    style: str,
    budget: int,
    seed: str = "",
    region: str = "",
    biome: str = "",
    prompt: str = "",
) -> Schematic:
    """把已校驗的設計編譯成 Schematic（超預算時確定性裁剪）。"""
    grid = VoxelGrid(design.width, design.height, design.length)
    for op in design.ops:
        _exec_op(grid, op)
    cap = max(16, min(int(budget), MAX_BLOCKS))
    if grid.solid_count() > cap:
        rng = random.Random(_seed_int(f"{seed}|llm-design|{design.kind}"))
        grid.trim_to(cap, rng)
    biome_id = (biome or REGION_BIOMES.get(region) or DEFAULT_BIOME).strip() or DEFAULT_BIOME
    if ":" not in biome_id:
        biome_id = f"minecraft:{biome_id}"
    schematic = grid.to_schematic(kind=design.kind, biome=biome_id)
    schematic.metadata = {
        "Name": (prompt or design.kind)[:80],
        "Author": "Linkin-LLM",
        "Date": ("long", int(time.time() * 1000)),
    }
    return schematic


# ── 對 LLM 的提示詞 ──


def build_design_prompt(*, prompt: str, style: str, region: str = "", block_count: int = 256) -> str:
    """組裝給 LLM 的設計任務提示詞（含調色盤、白名單、op 目錄與範例）。"""
    mats = palette_for_style(style)
    palette_lines = "\n".join(f"- {role} = {block}" for role, block in sorted(mats.items()))
    allowed = ", ".join(sorted(_ALLOWED_MATERIALS))
    budget = max(16, min(int(block_count), MAX_BLOCKS))
    example = json.dumps(_DESIGN_EXAMPLE, ensure_ascii=False)
    kinds = "/".join(sorted(KNOWN_KINDS))
    return f"""【建築需求】{prompt}
【區域】{region or '未指定'}
【風格】{style or '未指定'}
【方塊預算】非空氣方塊 ≤ {budget}（超出會被系統裁剪，請自行控制規模）
【畫布】size=[寬,高,深]，每軸 ≤ {MAX_DESIGN_AXIS}，體積 ≤ {MAX_DESIGN_VOLUME}；座標 x=寬、y=高（0 為地面）、z=深
【風格調色盤】material 可直接用角色名：
{palette_lines}
【通用材質白名單】也可用下列方塊（不帶 minecraft: 前綴亦可），air 用於鏤空門窗：
{allowed}
【建築種類】kind 從中選擇：{kinds}
【op 目錄】ops 依序執行，後者覆蓋前者：
- cuboid: x,y,z,w,h,d,material[,hollow]（hollow=true 只蓋外殼，適合牆體）
- line: x1,y1,z1,x2,y2,z2,material（直線：橋面、樑、欄杆、柱）
- column: x,y,z,height,material[,radius]（垂直圓柱：燈柱、塔柱；radius 預設 0）
- arch: x,y,z,span,height,material[,axis]（半圓拱：拱形橋體、門洞；axis=x 或 z）
- pyramid: x,y,z,w,d,height,material（階梯金字塔：神殿頂）
- gable: x,y,z,w,d,height,material（人字屋頂，脊沿 x 方向）
【硬性要求】
1. 只輸出一個 JSON 物件：{{"kind": "...", "size": [寬,高,深], "ops": [...]}}，無其他文字。
2. ops ≤ {MAX_OPS} 個；需求中的每個具體元素都必須有對應 op（如「燈柱」→ column + 頂部 accent 方塊）。
3. 材質只能用調色盤角色名或白名單方塊；建築要立在地面（y=0 起）。
【範例】小屋（地板＋鏤空牆＋門洞＋人字屋頂＋門邊燈柱）：
{example}"""


# ── 主入口 ──


def generate_llm_structure(
    *,
    prompt: str,
    style: str,
    block_count: int,
    seed: str = "",
    region: str = "",
    biome: str = "",
) -> tuple[Schematic, dict[str, Any]] | None:
    """LLM 理解需求並設計 3D 模型。

    回傳 (Schematic, design_payload)；開關關閉、無金鑰、LLM 失敗、
    輸出無法校驗或編譯結果為空時回傳 None（呼叫方降級程序化生成）。
    """
    if not design_enabled() or not _llm_ready():
        return None
    budget = max(16, min(int(block_count or 64), MAX_BLOCKS))
    task_prompt = build_design_prompt(
        prompt=prompt, style=style, region=region, block_count=budget
    )
    try:
        model_name = resolve_stage_model("generate", query=prompt)
        raw = call_llm(task_prompt, system=DESIGN_SYSTEM_PROMPT, model=model_name)
    except Exception as exc:  # noqa: BLE001 — LLM 失敗降級程序化生成
        logger.warning("LLM 建築設計呼叫失敗（降級程序化生成）：%s", exc)
        return None
    design = parse_design(raw or "", style=style, prompt=prompt)
    if design is None:
        logger.warning("LLM 建築設計輸出無效（降級程序化生成）；原始輸出前 200 字：%s", (raw or "")[:200])
        return None
    try:
        schematic = compile_design(
            design,
            style=style,
            budget=budget,
            seed=seed,
            region=region,
            biome=biome,
            prompt=prompt,
        )
    except Exception as exc:  # noqa: BLE001 — 編譯失敗降級程序化生成
        logger.warning("LLM 建築設計編譯失敗（降級程序化生成）：%s", exc)
        return None
    if schematic.solid_count() <= 0:
        logger.warning("LLM 建築設計編譯結果為空（降級程序化生成）")
        return None
    payload = design.to_payload()
    payload["model"] = str(model_name or "")
    logger.info(
        "LLM 建築設計成功：%s（%d ops，%d 方塊，%dx%dx%d）",
        design.kind,
        len(design.ops),
        schematic.solid_count(),
        design.width,
        design.height,
        design.length,
    )
    return schematic, payload
