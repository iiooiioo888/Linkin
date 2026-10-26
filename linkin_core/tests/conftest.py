"""讓階段 1 服務套件可被匯入。"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _rel in ("services/guardrail-service", "services/tool-gateway", "services/minecraft-gateway"):
    _path = str(_ROOT / _rel)
    if _path not in sys.path:
        sys.path.insert(0, _path)
