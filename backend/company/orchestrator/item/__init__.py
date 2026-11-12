"""工作項 mixin（ItemMixin）：單一工作項執行、席位 I/O 記錄、任務規格與工具權限判定。

第十三輪重構：ItemMixin 已拆成 item/_run.py（_execute_single_item）與
item/_seat.py（席位 I/O／任務規格／工具權限）兩個 mixin，於此組合；
方法本體與 docstring 逐字保留，orchestrator/__init__.py 的
from .item import ItemMixin 不需修改。
"""

from __future__ import annotations

from ._run import _ItemRunMixin
from ._seat import _ItemSeatMixin


class ItemMixin(_ItemRunMixin, _ItemSeatMixin):
    """單一工作項執行、席位 I/O 記錄、任務規格與工具權限判定。"""


__all__ = ["ItemMixin"]
