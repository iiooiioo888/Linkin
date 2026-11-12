"""標的別名正規化與交易所代碼推導。"""

from __future__ import annotations

import re

from ..constants import _SH_INDEX_CODES, SYMBOL_ALIASES


def normalize_symbol(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        raise ValueError("symbol 不可為空")
    alias = SYMBOL_ALIASES.get(text) or SYMBOL_ALIASES.get(text.replace(" ", ""))
    if alias:
        return alias
    if re.fullmatch(r"\d{6}", text):
        # 滬深指數代碼在上交所（000001.SZ 仍是平安銀行，指數請用別名「上證」）
        if text.startswith(("6", "9")) or text in _SH_INDEX_CODES:
            return f"{text}.SS"
        if text.startswith(("8", "4")):
            return f"{text}.BJ"
        return f"{text}.SZ"
    return text.upper() if text.isascii() else text

def _a_share_code(symbol: str) -> str | None:
    match = re.fullmatch(r"(\d{6})\.(SS|SZ|BJ)", symbol.upper())
    return match.group(1) if match else None

def _eastmoney_secid(symbol: str) -> str | None:
    match = re.fullmatch(r"(\d{6})\.(SS|SZ|BJ)", symbol.upper())
    if not match:
        return None
    code, exch = match.group(1), match.group(2)
    prefix = {"SS": "1", "SZ": "0", "BJ": "0"}.get(exch, "1")
    return f"{prefix}.{code}"

def _stooq_ticker(symbol: str) -> str | None:
    if _a_share_code(symbol):
        return None
    text = symbol.strip().lower()
    if "." not in text:
        return f"{text}.us"
    if text.endswith((".ss", ".sz", ".bj")):
        return None
    return text
