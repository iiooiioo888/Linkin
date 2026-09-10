"""stdin: 簡化或正式 Archify JSON → stdout: 正式 document。

給 Vite 外掛呼叫；實際 HTML 由 frontend 的 npm 依賴 archify CLI 渲染。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.company.archify_compile import compile_ir


def main() -> None:
    if len(sys.argv) > 1:
        raw = Path(sys.argv[1]).read_text(encoding="utf-8")
    else:
        raw = sys.stdin.buffer.read().decode("utf-8")
    if not raw.strip():
        raise SystemExit("需要 Archify IR JSON（stdin 或檔案路徑）")
    doc = compile_ir(json.loads(raw))
    json.dump(doc, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
