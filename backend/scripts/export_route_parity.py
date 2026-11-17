"""匯出路由基準快照，供元件化重構的 parity 測試比對。

用法::

    python -m backend.scripts.export_route_parity               # 寫入 docs/contracts/
    python -m backend.scripts.export_route_parity --check       # 比對內容集合（CI 用）
    python -m backend.scripts.export_route_parity --check-order # 額外比對宣告順序

**關於順序。** 快照記錄宣告順序，但元件化遷移**必然**改變它：各功能收進自己的
``APIRouter`` 後會聚成一塊。所以 ``--check`` 只比對「內容集合」
（path ＋ method ＋ name），與 ``test_route_set_matches_baseline`` 一致。

嚴格順序比對會讓這道鎖退化成「每批都要重生快照並重新批准」，
真正該攔下的問題（刪路由、改路徑、改 method）反而淹沒在雜訊裡。
順序唯一的實質風險 —— 同 method、同深度的字面路由被參數路由遮蔽 ——
由 ``test_literal_param_shadowing`` 專門守；``--check-order`` 只在需要
人工核對宣告順序時使用。

**重生不可無聲。** 不帶參數執行時，必定印出本次變更的路由差異清單
（新增／刪除的 path＋method＋name）。集合相等是硬條件，快照只是記錄現況。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT_PATH = ROOT / "docs" / "contracts" / "component-route-parity.json"
#: 快照以 master `c32977b`（#178）為基準——B0 分支 rebase 到該點後重生。
#: 先前的 `eb14f83` 是 317 條；master 後續合入 #179–#193 新增 3 條（320 條）。
BASELINE_COMMIT = "c32977b"


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


def _content_key(route: dict) -> tuple[str, tuple[str, ...], str]:
    return (str(route["path"]), tuple(sorted(route.get("methods") or [])), str(route.get("name") or ""))


def _diff_lines(
    previous: set[tuple[str, tuple[str, ...], str]],
    current: set[tuple[str, tuple[str, ...], str]],
) -> list[str]:
    """產生人類可讀的路由差異（給重生輸出與 PR 說明貼用）。"""
    missing = previous - current
    added = current - previous

    def fmt(item: tuple[str, tuple[str, ...], str]) -> str:
        path, methods, name = item
        return f"{'/'.join(methods) or 'WS':6s} {path}  (name={name or '-'})"

    lines: list[str] = []
    if not missing and not added:
        lines.append("路由差異：空集合（0 新增 / 0 刪除）")
        return lines
    lines.append(f"路由差異：+{len(added)} / -{len(missing)}")
    for item in sorted(added):
        lines.append(f"  + {fmt(item)}")
    for item in sorted(missing):
        lines.append(f"  - {fmt(item)}")
    return lines


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    check = "--check" in args
    check_order = "--check-order" in args
    payload = build_payload()
    text = dumps(payload)

    previous: set[tuple[str, tuple[str, ...], str]] = set()
    if OUT_PATH.exists():
        previous = {
            _content_key(r) for r in json.loads(OUT_PATH.read_text(encoding="utf-8"))["routes"]
        }

    if check or check_order:
        if not OUT_PATH.exists():
            print(f"缺少基準快照：{OUT_PATH}", file=sys.stderr)
            return 1
        actual = {_content_key(r) for r in payload["routes"]}

        missing = previous - actual
        added = actual - previous
        if missing or added:
            for item in sorted(missing)[:10]:
                print(f"路由消失：{item}", file=sys.stderr)
            for item in sorted(added)[:10]:
                print(f"新增路由：{item}", file=sys.stderr)
            return 1

        if check_order:
            if OUT_PATH.read_text(encoding="utf-8") != text:
                print(
                    f"宣告順序已變（內容一致）：{OUT_PATH}\n"
                    "順序變更屬元件化的預期結果；只有字面/參數遮蔽才有風險，"
                    "見 test_literal_param_shadowing。",
                    file=sys.stderr,
                )
                return 1
            print(f"路由快照一致（{payload['count']} 條，含順序）")
            return 0

        print(f"路由內容一致（{payload['count']} 條；順序另見 --check-order）")
        return 0

    # 重生：**必須**印出本次差異，不可無聲覆寫。
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(text, encoding="utf-8")
    print(f"Wrote {OUT_PATH} ({payload['count']} routes)")
    print("── 本次快照變更（請貼進 PR 說明）──")
    current = {_content_key(r) for r in payload["routes"]}
    for line in _diff_lines(previous, current):
        print(line)
    if previous and previous != current:
        print("⚠ 集合不相等：請確認是預期變更，並在 PR 說明列出原因。")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
