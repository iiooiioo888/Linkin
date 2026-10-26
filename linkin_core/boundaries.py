"""依賴方向。契約套件不得引用運行時服務。"""

from __future__ import annotations

import ast
from pathlib import Path

FORBIDDEN_ROOTS = frozenset(
    {
        "backend",
        "opc_service",
        "frontend",
        "fastapi",
        "uvicorn",
        "nats",
        "kubernetes",
        "redis",
        "chromadb",
    }
)


def _imported_modules(tree: ast.AST) -> list[str]:
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)
    return found


def forbidden_imports(root: Path | None = None) -> list[str]:
    base = root or Path(__file__).resolve().parent
    violations: list[str] = []
    for path in sorted(base.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for module in _imported_modules(tree):
            top = module.split(".", 1)[0]
            if top in FORBIDDEN_ROOTS:
                rel = path.relative_to(base.parent)
                violations.append(f"{rel}: {module}")
    return violations
