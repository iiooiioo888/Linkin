"""以 nbtlib 產生 WorldEdit 可用的 .schem，並印出 Base64。

範例：

    python -m backend.scripts.build_schem
    python -m backend.scripts.build_schem --out small_house.schem --print-b64
"""

from __future__ import annotations

import argparse
from pathlib import Path

from backend.linkin.schematic import (
    SPONGE_VERSION,
    build_small_house_schematic,
    encode_schematic,
    schematic_to_base64,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="產生 Sponge Schematic v3（.schem）與 Base64")
    parser.add_argument("--out", default="small_house.schem", help="輸出 .schem 路徑")
    parser.add_argument("--name", default="小型避難所")
    parser.add_argument("--print-b64", action="store_true", default=True, help="印出 Base64（預設開啟）")
    parser.add_argument("--no-print-b64", action="store_false", dest="print_b64")
    args = parser.parse_args()

    model = build_small_house_schematic(name=args.name)
    raw = encode_schematic(model, version=SPONGE_VERSION)
    out = Path(args.out)
    out.write_bytes(raw)
    print(f"已生成 {out.resolve()}（Gzip NBT / Sponge v{SPONGE_VERSION} / {model.solid_count()} 方塊）")
    print("WorldEdit：//schem load 後 //paste；FAWE 同樣支援 Sponge v3。")
    if args.print_b64:
        print("Base64 編碼內容（直接複製，不含引號）：")
        print(schematic_to_base64(model, version=SPONGE_VERSION))


if __name__ == "__main__":
    main()
