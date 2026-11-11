"""匯出組件 manifest，供前端讀取同一份契約。

產物兩份（同一內容，不同消費者）：

- ``frontend/src/generated/component-manifest.json`` — 前端 import（``resolveJsonModule`` 已開）
- ``docs/contracts/component-manifest.json`` — 外部客戶端與文件引用

兩份都**提交進 git**，理由：GitHub Pages 離線與後端不可達時前端仍要能渲染導覽。
這與 ``frontend/src/generated/monitor-fallback.json`` 是同一機制，
因此不需要改 ``.github/workflows/deploy-pages.yml``。

用法::

    python -m backend.scripts.export_component_manifest           # 寫檔
    python -m backend.scripts.export_component_manifest --check   # CI 比對（不落盤）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FRONTEND_PATH = ROOT / "frontend" / "src" / "generated" / "component-manifest.json"
DOCS_PATH = ROOT / "docs" / "contracts" / "component-manifest.json"


def build_payload() -> dict:
    """建構 manifest（純函式，不落盤）。"""
    from backend.modules.component_registry import component_manifest, get_builtin_components

    return component_manifest(get_builtin_components())


def dumps(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    check = "--check" in args
    text = dumps(build_payload())

    if check:
        drifted: list[Path] = []
        for path in (FRONTEND_PATH, DOCS_PATH):
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                drifted.append(path)
        if drifted:
            for path in drifted:
                print(f"manifest 已漂移：{path}", file=sys.stderr)
            return 1
        print("manifest 一致")
        return 0

    for path in (FRONTEND_PATH, DOCS_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
