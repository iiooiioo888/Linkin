#!/usr/bin/env python3
"""以反向檔案順序執行 backend/tests（無 pytest-randomly 時的順序穩定性檢查）。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    tests_dir = root / "backend" / "tests"
    files = sorted(tests_dir.glob("test_*.py"), reverse=True)
    if not files:
        print("no test files", file=sys.stderr)
        return 1
    args = [
        sys.executable,
        "-m",
        "pytest",
        "-p",
        "no:cacheprovider",
        *map(str, files),
    ]
    print("Running:", " ".join(args[:8]), f"... (+{len(files)} files)")
    return subprocess.call(args, cwd=root)


if __name__ == "__main__":
    raise SystemExit(main())
