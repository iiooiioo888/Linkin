#!/usr/bin/env python3
"""從 log 聚合 G-OBS1 path 事件（g_obs1_path_event=1）。

用法：
  python backend/scripts/aggregate_g_obs1_path_counts.py logfile
  journalctl -u linkin-api --since "24 hours ago" | python backend/scripts/aggregate_g_obs1_path_counts.py

僅解析結構化列；不連產線、不改 WIRE、不 reset 計數。
"""

from __future__ import annotations

import re
import sys
from collections import Counter

_EVENT = re.compile(
    r"g_obs1_path_event=1\s+path=(?P<path>via|bypass|would_block)\b"
)


def aggregate_lines(lines) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for line in lines:
        m = _EVENT.search(line)
        if m:
            counts[m.group("path")] += 1
    return {
        "via": int(counts.get("via", 0)),
        "bypass": int(counts.get("bypass", 0)),
        "would_block": int(counts.get("would_block", 0)),
        "events_total": int(sum(counts.values())),
    }


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        with open(argv[1], encoding="utf-8", errors="replace") as fh:
            result = aggregate_lines(fh)
    else:
        result = aggregate_lines(sys.stdin)
    print(
        "g_obs1_aggregate "
        f"via={result['via']} bypass={result['bypass']} "
        f"would_block={result['would_block']} events_total={result['events_total']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
