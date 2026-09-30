"""LangGraph 安全地板。

地板測試只拒絕已知有漏洞的舊版，不鎖定 pip 解析到的精確版本。
未使用 checkpointer 時，嚴格 msgpack 不會執行反序列化。
"""

from __future__ import annotations

import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS = (ROOT / "requirements.txt").read_text(encoding="utf-8")


def _requirement_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped and not stripped.startswith("#"):
            lines.append(stripped)
    return lines


def _version_tuple(raw: str) -> tuple[int, ...]:
    core = raw.split("+", 1)[0]
    parts: list[int] = []
    for piece in core.split("."):
        digits = ""
        for ch in piece:
            if ch.isdigit():
                digits += ch
            else:
                break
        if digits:
            parts.append(int(digits))
    return tuple(parts)


def test_requirements_pin_security_floor_without_sqlite_extra() -> None:
    lines = _requirement_lines(REQUIREMENTS)
    assert "langgraph>=1.0.10" in lines
    assert "langgraph-checkpoint>=3.0.0" in lines
    assert not any(line.startswith("langgraph-checkpoint-sqlite") for line in lines)
    assert not any(line.startswith("langgraph>=") and "0.2" in line for line in lines)


def test_installed_langgraph_meets_security_floor() -> None:
    assert _version_tuple(version("langgraph")) >= (1, 0, 10)
    assert _version_tuple(version("langgraph-checkpoint")) >= (3, 0, 0)
    try:
        sqlite_version = version("langgraph-checkpoint-sqlite")
    except PackageNotFoundError:
        return
    assert _version_tuple(sqlite_version) >= (3, 0, 1)


def test_strict_msgpack_is_read_before_checkpoint_import() -> None:
    script = (
        "import opc_service.msgpack_safety\n"
        "from langgraph.checkpoint.serde import _msgpack\n"
        "assert _msgpack.STRICT_MSGPACK_ENABLED is True\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_graph_modules_import_safety_before_langgraph() -> None:
    for relative in ("backend/core/graph.py", "opc_service/graph.py"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        safety = text.find("import opc_service.msgpack_safety")
        langgraph = text.find("from langgraph.graph import")
        assert safety != -1, relative
        assert langgraph != -1, relative
        assert safety < langgraph, relative


def test_containers_set_strict_msgpack_at_process_start() -> None:
    """ENV 行是 ASCII。先對 bytes 斷言，註解編碼壞掉時仍能指出缺的是哪一行。"""
    compose = (ROOT / "docker-compose.yml").read_bytes()
    assert compose.count(b"LANGGRAPH_STRICT_MSGPACK=true") >= 2
    compose.decode("utf-8")
    for relative in ("backend/Dockerfile", "opc_service/Dockerfile"):
        data = (ROOT / relative).read_bytes()
        assert b"ENV LANGGRAPH_STRICT_MSGPACK=true" in data, relative
        data.decode("utf-8")
