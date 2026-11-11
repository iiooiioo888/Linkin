"""匯出 OpenAPI 基準快照，供元件化重構的契約比對。

與 ``docs/openapi.json`` 的分工：

- ``docs/openapi.json`` 是**對外發布**的 OpenAPI 匯出（``export_openapi.py``），
  歷史上已過期且 ``info.title`` 與程式不符，本輪不動它。
- ``docs/contracts/openapi-snapshot.json`` 是**重構安全網**：
  從當前 master 現場生成，只在意 paths／schemas 是否在重構中漂移。

用法::

    python -m backend.scripts.export_openapi_snapshot           # 寫檔
    python -m backend.scripts.export_openapi_snapshot --check   # CI 比對
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT_PATH = ROOT / "docs" / "contracts" / "openapi-snapshot.json"
BASELINE_COMMIT = "eb14f83"


#: 已存在的不穩定欄位：``backend/modules/api.py`` 的 ``world_module_api``
#: 用同一個 handler 掛 5 個 HTTP method（``api_route(methods=[...])``），
#: FastAPI 從 set 迭代序推 ``operationId``，每次 import 都可能不同
#: （實測 ``…__get`` / ``…__put`` / ``…__post`` 三種都出現過）。
#: 這是**既有 bug**（OpenAPI 也會印 Duplicate Operation ID 警告），
#: 不屬元件化範圍；快照對這條路徑的 ``operationId`` 做正規化，避免隨機紅燈。
_UNSTABLE_OPERATION_ID_PATHS: frozenset[str] = frozenset({"/modules/{module_id}/api/{path}"})
_OPERATION_ID_PLACEHOLDER = "<multi-method-handler:unstable>"


def _normalize_paths(paths: dict) -> dict:
    """對已知不穩定的 operationId 做正規化（其餘欄位一字不動）。"""
    normalized = {}
    for path, operations in paths.items():
        if path not in _UNSTABLE_OPERATION_ID_PATHS:
            normalized[path] = operations
            continue
        normalized[path] = {
            method: {**op, "operationId": _OPERATION_ID_PLACEHOLDER}
            if "operationId" in op
            else op
            for method, op in operations.items()
        }
    return normalized


def build_payload() -> dict:
    """建構快照內容（純函式，不落盤）。

    必須在 import ``backend.main`` 之前設 ``LINKIN_ENABLE_DOCS``，
    讓 ``app.openapi_url`` 的行為與文件環境一致。
    """
    os.environ.setdefault("LINKIN_ENABLE_DOCS", "1")
    from backend.main import app

    spec = app.openapi()
    paths = _normalize_paths(spec.get("paths") or {})
    return {
        "schema_version": 1,
        "baseline_commit": BASELINE_COMMIT,
        "path_count": len(paths),
        "operation_count": sum(len(ops) for ops in paths.values()),
        "normalized_paths": sorted(_UNSTABLE_OPERATION_ID_PATHS),
        "paths": paths,
        "components": spec.get("components") or {},
        "tags": spec.get("tags") or [],
    }


def dumps(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    check = "--check" in args
    payload = build_payload()
    text = dumps(payload)

    if check:
        if not OUT_PATH.exists():
            print(f"缺少基準快照：{OUT_PATH}", file=sys.stderr)
            return 1
        if OUT_PATH.read_text(encoding="utf-8") != text:
            print(f"OpenAPI 快照已漂移：{OUT_PATH}", file=sys.stderr)
            return 1
        print(f"OpenAPI 快照一致（{payload['path_count']} paths / {payload['operation_count']} operations）")
        return 0

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(text, encoding="utf-8")
    print(
        f"Wrote {OUT_PATH} "
        f"({payload['path_count']} paths / {payload['operation_count']} operations)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
