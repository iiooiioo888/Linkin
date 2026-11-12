"""把簡化 IR 編成 tt-a1i/archify 正式 JSON，並呼叫其 CLI 產出 HTML。

依賴：`frontend` 的 `archify`（file:../vendor/archify），找不到 npm 連結時回退 vendor/archify。

本檔案已於第十二輪重構拆為套件：對外仍以
from backend.company.archify_compile import compile_ir, render_view 等名稱匯入；
實作分散在 labels／layout／ir／diagrams／compile 等模組，內容與行為逐字不變。
"""

from __future__ import annotations

# 以下名稱是重構前模組的順帶轉出（dir() 公開集合的一部分），保留以維持相容
import hashlib  # noqa: F401
import itertools  # noqa: F401
import json  # noqa: F401
import math  # noqa: F401
import os  # noqa: F401
import re  # noqa: F401
import shutil  # noqa: F401
import subprocess  # noqa: F401
import tempfile  # noqa: F401
from pathlib import Path  # noqa: F401
from typing import Any  # noqa: F401

from backend.company.quant_strategy_maps import (  # noqa: F401
    ARCHIFY_SOURCE,
    archify_strategies,
    strategy_catalog_maps,
    strategy_maps,
)

# 舊模組私有 helper 的頂層名稱相容（all-names 基線）
from .compile import (  # noqa: F401  # noqa: F401
    CACHE_DIR,
    ROOT,
    _node_executable,
    _prepare_html,
    archify_bin,
    archify_root,
    compile_ir,
    render_document,
    render_ir,
    render_view,
    resolve_strategy_ir,
)
from .diagrams import _compile_dataflow, _compile_lifecycle  # noqa: F401
from .ir import (  # noqa: F401
    _ROLE_LAYER,
    _ROLE_TYPE,
    _compile_architecture,
    _compile_workflow,
    _edges,
    _is_official,
    _kind,
    _meta,
    _nodes,
)
from .labels import _ID_RE, _compact, _short_label, _sid  # noqa: F401
from .layout import _grid_spine, _named_connections  # noqa: F401

# 子模組名稱不留在套件公開命名空間（維持重構前 dir() 的公開名稱集合）
for _submodule in ("compile", "diagrams", "ir", "labels", "layout"):
    globals().pop(_submodule, None)
del _submodule
