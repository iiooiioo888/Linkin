"""LVS 不得依賴公司席位、計費、Hub 或 LLM 呼叫層。"""

from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1] / "local_video_studio"
_FORBIDDEN = (
    "backend.company",
    "backend.billing",
    "backend.hub",
    "backend.core.llm",
)


def _forbidden(module: str) -> str | None:
    for prefix in _FORBIDDEN:
        if module == prefix or module.startswith(prefix + "."):
            return prefix
    return None


def _imported_modules(tree: ast.AST) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if base == "backend.core":
                for alias in node.names:
                    if alias.name == "llm" or alias.name.startswith("llm."):
                        found.append((node.lineno, "backend.core.llm"))
            if base:
                found.append((node.lineno, base))
        elif isinstance(node, ast.Call):
            func = node.func
            name = ""
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name in {"import_module", "__import__"} and node.args:
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    found.append((node.lineno, arg.value))
    return found


def test_lvs_package_has_no_forbidden_imports():
    files = sorted(_ROOT.rglob("*.py"))
    assert files, "local_video_studio 套件應有 Python 檔"
    violations: list[str] = []
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for lineno, module in _imported_modules(tree):
            hit = _forbidden(module)
            if hit:
                violations.append(f"{path}:{lineno} imports {module} ({hit})")
    assert violations == []
