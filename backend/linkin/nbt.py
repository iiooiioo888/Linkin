"""精簡 NBT 編解碼（Gzip + Java 大端），供 Sponge Schematic 使用。"""

from __future__ import annotations

import gzip
import struct
from io import BytesIO
from typing import Any

TAG_END = 0
TAG_BYTE = 1
TAG_SHORT = 2
TAG_INT = 3
TAG_LONG = 4
TAG_FLOAT = 5
TAG_DOUBLE = 6
TAG_BYTE_ARRAY = 7
TAG_STRING = 8
TAG_LIST = 9
TAG_COMPOUND = 10
TAG_INT_ARRAY = 11
TAG_LONG_ARRAY = 12

_MAX_DEPTH = 64


class NbtError(ValueError):
    """NBT 結構無法解析或寫入。"""


class NbtList(list):
    """帶元素型別的 NBT List，空列表時仍需知道 type_id。"""

    def __init__(self, type_id: int, items: list[Any] | None = None):
        super().__init__(items or [])
        self.type_id = int(type_id)


def dumps(name: str, tag: dict[str, Any]) -> bytes:
    buf = BytesIO()
    _write_named(buf, TAG_COMPOUND, name, tag)
    return buf.getvalue()


def dumps_gzip(name: str, tag: dict[str, Any]) -> bytes:
    return gzip.compress(dumps(name, tag))


def loads(data: bytes) -> tuple[str, dict[str, Any]]:
    buf = BytesIO(data)
    type_id = _read_u8(buf)
    if type_id != TAG_COMPOUND:
        raise NbtError(f"根標籤必須為 TAG_Compound，收到 {type_id}")
    name = _read_string(buf)
    payload = _read_payload(buf, TAG_COMPOUND, depth=0)
    if not isinstance(payload, dict):
        raise NbtError("根複合標籤無效")
    return name, payload


def loads_gzip(data: bytes) -> tuple[str, dict[str, Any]]:
    if len(data) >= 2 and data[0] == 0x1F and data[1] == 0x8B:
        try:
            raw = gzip.decompress(data)
        except OSError as exc:
            raise NbtError("Gzip 解壓失敗") from exc
        return loads(raw)
    return loads(data)


def _read_u8(buf: BytesIO) -> int:
    raw = buf.read(1)
    if len(raw) != 1:
        raise NbtError("非預期的檔案結尾")
    return raw[0]


def _read_exact(buf: BytesIO, n: int) -> bytes:
    raw = buf.read(n)
    if len(raw) != n:
        raise NbtError("非預期的檔案結尾")
    return raw


def _read_string(buf: BytesIO) -> str:
    length = struct.unpack(">H", _read_exact(buf, 2))[0]
    if length == 0:
        return ""
    return _read_exact(buf, length).decode("utf-8", errors="replace")


def _write_string(buf: BytesIO, value: str) -> None:
    encoded = (value or "").encode("utf-8")
    if len(encoded) > 65535:
        raise NbtError("字串超過 65535 位元組")
    buf.write(struct.pack(">H", len(encoded)))
    buf.write(encoded)


def _read_payload(buf: BytesIO, type_id: int, *, depth: int) -> Any:
    if depth > _MAX_DEPTH:
        raise NbtError("NBT 巢狀過深")
    if type_id == TAG_BYTE:
        return struct.unpack(">b", _read_exact(buf, 1))[0]
    if type_id == TAG_SHORT:
        return struct.unpack(">h", _read_exact(buf, 2))[0]
    if type_id == TAG_INT:
        return struct.unpack(">i", _read_exact(buf, 4))[0]
    if type_id == TAG_LONG:
        return struct.unpack(">q", _read_exact(buf, 8))[0]
    if type_id == TAG_FLOAT:
        return struct.unpack(">f", _read_exact(buf, 4))[0]
    if type_id == TAG_DOUBLE:
        return struct.unpack(">d", _read_exact(buf, 8))[0]
    if type_id == TAG_BYTE_ARRAY:
        length = struct.unpack(">i", _read_exact(buf, 4))[0]
        if length < 0:
            raise NbtError("負長度 byte array")
        return _read_exact(buf, length)
    if type_id == TAG_STRING:
        return _read_string(buf)
    if type_id == TAG_LIST:
        elem_type = _read_u8(buf)
        length = struct.unpack(">i", _read_exact(buf, 4))[0]
        if length < 0:
            raise NbtError("負長度 list")
        items = [_read_payload(buf, elem_type, depth=depth + 1) for _ in range(length)]
        return NbtList(elem_type, items)
    if type_id == TAG_COMPOUND:
        out: dict[str, Any] = {}
        while True:
            child_type = _read_u8(buf)
            if child_type == TAG_END:
                break
            child_name = _read_string(buf)
            out[child_name] = _read_payload(buf, child_type, depth=depth + 1)
        return out
    if type_id == TAG_INT_ARRAY:
        length = struct.unpack(">i", _read_exact(buf, 4))[0]
        if length < 0:
            raise NbtError("負長度 int array")
        return list(struct.unpack(f">{length}i", _read_exact(buf, 4 * length))) if length else []
    if type_id == TAG_LONG_ARRAY:
        length = struct.unpack(">i", _read_exact(buf, 4))[0]
        if length < 0:
            raise NbtError("負長度 long array")
        return list(struct.unpack(f">{length}q", _read_exact(buf, 8 * length))) if length else []
    raise NbtError(f"未知 NBT 標籤 {type_id}")


def _write_named(buf: BytesIO, type_id: int, name: str, value: Any) -> None:
    buf.write(struct.pack(">B", type_id))
    _write_string(buf, name)
    _write_payload(buf, type_id, value)


def _write_payload(buf: BytesIO, type_id: int, value: Any) -> None:
    if type_id == TAG_BYTE:
        buf.write(struct.pack(">b", int(value)))
        return
    if type_id == TAG_SHORT:
        buf.write(struct.pack(">h", int(value)))
        return
    if type_id == TAG_INT:
        buf.write(struct.pack(">i", int(value)))
        return
    if type_id == TAG_LONG:
        buf.write(struct.pack(">q", int(value)))
        return
    if type_id == TAG_FLOAT:
        buf.write(struct.pack(">f", float(value)))
        return
    if type_id == TAG_DOUBLE:
        buf.write(struct.pack(">d", float(value)))
        return
    if type_id == TAG_BYTE_ARRAY:
        raw = bytes(value) if not isinstance(value, bytes) else value
        buf.write(struct.pack(">i", len(raw)))
        buf.write(raw)
        return
    if type_id == TAG_STRING:
        _write_string(buf, str(value))
        return
    if type_id == TAG_LIST:
        if isinstance(value, NbtList):
            elem_type = value.type_id
            items = list(value)
        elif isinstance(value, list):
            items = value
            elem_type = TAG_COMPOUND if items and isinstance(items[0], dict) else TAG_END
        else:
            raise NbtError("TAG_List 需要 list")
        buf.write(struct.pack(">B", elem_type))
        buf.write(struct.pack(">i", len(items)))
        for item in items:
            _write_payload(buf, elem_type, item)
        return
    if type_id == TAG_COMPOUND:
        if not isinstance(value, dict):
            raise NbtError("TAG_Compound 需要 dict")
        for key, item in value.items():
            child_type, child_value = _typed_item(item)
            _write_named(buf, child_type, str(key), child_value)
        buf.write(b"\x00")
        return
    if type_id == TAG_INT_ARRAY:
        items = [int(v) for v in value]
        buf.write(struct.pack(">i", len(items)))
        if items:
            buf.write(struct.pack(f">{len(items)}i", *items))
        return
    if type_id == TAG_LONG_ARRAY:
        items = [int(v) for v in value]
        buf.write(struct.pack(">i", len(items)))
        if items:
            buf.write(struct.pack(f">{len(items)}q", *items))
        return
    raise NbtError(f"未知 NBT 標籤 {type_id}")


def _typed_item(value: Any) -> tuple[int, Any]:
    """為 schematic 寫入推斷型別；顯式 tuple ('short', 3) 可覆寫。"""
    if isinstance(value, tuple) and len(value) == 2 and value[0] in _TYPE_ALIASES:
        alias, inner = value
        return _TYPE_ALIASES[alias], inner
    if isinstance(value, NbtList):
        return TAG_LIST, value
    if isinstance(value, dict):
        return TAG_COMPOUND, value
    if isinstance(value, (bytes, bytearray)):
        return TAG_BYTE_ARRAY, bytes(value)
    if isinstance(value, bool):
        return TAG_BYTE, 1 if value else 0
    if isinstance(value, int):
        if -2147483648 <= value <= 2147483647:
            return TAG_INT, value
        return TAG_LONG, value
    if isinstance(value, float):
        return TAG_DOUBLE, value
    if isinstance(value, str):
        return TAG_STRING, value
    if isinstance(value, list):
        if value and all(isinstance(v, int) for v in value):
            return TAG_INT_ARRAY, value
        return TAG_LIST, NbtList(TAG_COMPOUND, value)
    raise NbtError(f"無法推斷 NBT 型別：{type(value)!r}")


_TYPE_ALIASES = {
    "byte": TAG_BYTE,
    "short": TAG_SHORT,
    "int": TAG_INT,
    "long": TAG_LONG,
    "float": TAG_FLOAT,
    "double": TAG_DOUBLE,
    "byte_array": TAG_BYTE_ARRAY,
    "string": TAG_STRING,
    "list": TAG_LIST,
    "compound": TAG_COMPOUND,
    "int_array": TAG_INT_ARRAY,
    "long_array": TAG_LONG_ARRAY,
}
