"""檢查要用 CLI 才能執行的技能是否已安裝對應命令。

    python -m backend.scripts.cli_runtimes
    python -m backend.scripts.cli_runtimes --json

只讀 PATH，不安裝套件、不讀取 ~/.agent-reach 或其他憑證。
"""

from __future__ import annotations

import argparse
import json
import sys

from backend.company.cli_runtimes import format_status, probe_all


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="檢查 CLI 技能運行時")
    parser.add_argument("--json", action="store_true", help="以 JSON 輸出")
    args = parser.parse_args(argv)
    rows = probe_all()
    if args.json:
        json.dump({"runtimes": rows}, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        print(format_status(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
