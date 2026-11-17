"""匯出路由基準快照，供元件化重構的 parity 測試比對。

用法::

    python -m backend.scripts.export_route_parity              # 寫入 docs/contracts/
    python -m backend.scripts.export_route_parity --check      # 只比對，不寫檔（CI 用）

快照記錄**宣告順序**。元件化遷移會改變全域順序（各功能收進自己的
``APIRouter`` 後必然聚成一塊），所以正式驗收用的是
``test_route_set_matches_baseline``（集合相等）；順序只用於
``test_literal_param_shadowing_unchanged`` 這類遮蔽檢查。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT_PATH = ROOT / "docs" / "contracts" / "component-route-parity.json"
BASELINE_COMMIT = "eb14f83"


def build_payload() -> dict:
    """建構快照內容（純函式，不落盤）。"""
    from backend.main import app
    from backend.scripts.route_table import flatten_routes

    entries = flatten_routes(app.routes)
    return {
        "schema_version": 1,
        "baseline_commit": BASELINE_COMMIT,
        "count": len(entries),
        "routes": [entry.to_dict() for entry in entries],
    }


def dumps(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    check = "--check" in args
    payload = build_payload()
    text = dumps(payload)

    if check:
        if not OUT_PATH.exists():
            print(f"缺少基準快照：{OUT_PATH}", file=sys.stderr)
            return 1
        current = OUT_PATH.read_text(encoding="utf-8")
        if current != text:
            print(f"路由快照已漂移：{OUT_PATH}", file=sys.stderr)
            return 1
        print(f"路由快照一致（{payload['count']} 條）")
        return 0

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(text, encoding="utf-8")
    print(f"Wrote {OUT_PATH} ({payload['count']} routes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
