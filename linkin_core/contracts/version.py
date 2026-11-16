"""契約版本。

SCHEMA_VERSION：破壞性變更才升。這次 ``auto`` 仍接受並映射，不是移除，所以不升。
CONTRACT_VERSION：凍結快照日期，寫進 OpenAPI / AsyncAPI 的 ``info.version``。
RULE_PACK_VERSION：規則鏈日期。規則鏈沒動，不跟著這次快照走。
"""

SCHEMA_VERSION = "1.0.0"
CONTRACT_VERSION = "2026-11-16"
RULE_PACK_VERSION = "2026-10-26"

# 跟 SCHEMA_VERSION 的主版本走，不是另一套版號。
# 主版本小於或等於這個值時，auto 輸入映射為 user_default，不回 4xx。
# 現行 1.0.0 在窗口內；最早可以改成拒絕的是 2.0.0。
AUTO_INPUT_ACCEPTED_THROUGH_MAJOR = 1


def schema_major(version: str | None = None) -> int:
    text = SCHEMA_VERSION if version is None else version
    head, _, _ = text.partition(".")
    return int(head)


def auto_input_is_mapped(version: str | None = None) -> bool:
    """現行大版本內保留 auto 輸入映射。下一個大版本才允許改成拒絕。"""
    return schema_major(version) <= AUTO_INPUT_ACCEPTED_THROUGH_MAJOR
