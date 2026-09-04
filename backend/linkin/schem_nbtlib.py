"""以 nbtlib 寫出 Gzip NBT（.schem），供 WorldEdit / FAWE 載入。"""

from __future__ import annotations

import gzip
from io import BytesIO
from typing import Any

from nbtlib import File
from nbtlib.tag import (
    Byte,
    ByteArray,
    Compound,
    Double,
    Float,
    Int,
    IntArray,
    List,
    Long,
    LongArray,
    Short,
    String,
)

from backend.linkin import nbt

_ALIAS_CTORS = {
    "byte": Byte,
    "short": Short,
    "int": Int,
    "long": Long,
    "float": Float,
    "double": Double,
    "string": String,
}


def dumps_gzip(root_name: str, payload: dict[str, Any]) -> bytes:
    """把 typed dict 寫成 Java 大端 Gzip NBT（根名稱可為空字串）。"""
    compound = to_compound(payload)
    nbt_file = File(compound, gzipped=True, root_name=str(root_name))
    buf = BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0, compresslevel=6) as gz:
        nbt_file.write(gz)
    return buf.getvalue()


def to_compound(value: dict[str, Any]) -> Compound:
    converted = to_tag(value)
    if not isinstance(converted, Compound):
        raise TypeError("根節點必須是 Compound")
    return converted


def to_tag(value: Any) -> Any:
    if isinstance(value, tuple) and len(value) == 2 and value[0] in _ALIAS_CTORS:
        kind, inner = value
        return _ALIAS_CTORS[kind](inner)
    if isinstance(value, tuple) and len(value) == 2 and value[0] == "byte_array":
        return _byte_array(inner_bytes(value[1]))
    if isinstance(value, tuple) and len(value) == 2 and value[0] == "int_array":
        return IntArray([int(v) for v in value[1]])
    if isinstance(value, tuple) and len(value) == 2 and value[0] == "long_array":
        return LongArray([int(v) for v in value[1]])
    if isinstance(value, tuple) and len(value) == 2 and value[0] in {"list", "compound"}:
        return to_tag(value[1])
    if isinstance(value, nbt.NbtList):
        return _from_nbt_list(value)
    if isinstance(value, dict):
        return Compound({str(key): to_tag(item) for key, item in value.items()})
    if isinstance(value, (bytes, bytearray)):
        return _byte_array(bytes(value))
    if isinstance(value, bool):
        return Byte(1 if value else 0)
    if isinstance(value, int):
        if -2147483648 <= value <= 2147483647:
            return Int(value)
        return Long(value)
    if isinstance(value, float):
        return Double(value)
    if isinstance(value, str):
        return String(value)
    if isinstance(value, list):
        if value and all(isinstance(item, int) and not isinstance(item, bool) for item in value):
            return IntArray([int(item) for item in value])
        if not value:
            return List[Compound]([])
        if all(isinstance(item, dict) for item in value):
            return List[Compound]([to_compound(item) for item in value])
        if all(isinstance(item, float) for item in value):
            return List[Double]([Double(float(item)) for item in value])
        if all(isinstance(item, str) for item in value):
            return List[String]([String(item) for item in value])
        return List[Compound]([to_tag(item) for item in value])
    raise TypeError(f"無法轉成 nbtlib 標籤：{type(value)!r}")


def inner_bytes(value: Any) -> bytes:
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if isinstance(value, list):
        return bytes(int(item) & 0xFF for item in value)
    return bytes(value)


def _byte_array(data: bytes) -> ByteArray:
    signed = [byte - 256 if byte > 127 else byte for byte in data]
    return ByteArray(signed)


def _from_nbt_list(value: nbt.NbtList) -> Any:
    type_id = int(value.type_id)
    if type_id == nbt.TAG_COMPOUND:
        return List[Compound]([to_compound(item) if isinstance(item, dict) else to_tag(item) for item in value])
    if type_id == nbt.TAG_DOUBLE:
        return List[Double]([Double(float(item)) for item in value])
    if type_id == nbt.TAG_FLOAT:
        return List[Float]([Float(float(item)) for item in value])
    if type_id == nbt.TAG_INT:
        return List[Int]([Int(int(item)) for item in value])
    if type_id == nbt.TAG_STRING:
        return List[String]([String(str(item)) for item in value])
    if type_id == nbt.TAG_BYTE:
        return List[Byte]([Byte(int(item)) for item in value])
    if type_id == nbt.TAG_SHORT:
        return List[Short]([Short(int(item)) for item in value])
    if type_id == nbt.TAG_LONG:
        return List[Long]([Long(int(item)) for item in value])
    if type_id == nbt.TAG_END:
        return List[Compound]([])
    return List[Compound]([to_tag(item) for item in value])
