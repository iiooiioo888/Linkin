"""將 .agents/skills/ 同步進 Linkin 運行時 skills.json 與 mcp_servers.json。

用法（倉庫根目錄）：
    python -m backend.scripts.sync_agent_skills
"""

from __future__ import annotations

import json
import logging
import sys

from backend.company.agent_skills_sync import sync_agent_skills

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def main() -> int:
    report = sync_agent_skills()
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
