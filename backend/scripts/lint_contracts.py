"""契約靜態檢查（CI lint）：對齊 docs/contracts/runtime.md。

規則：
- ``no_direct_provider_sdk``（C-LLM-001，P0）：業務代碼禁止直接 import
  模型供應商 SDK；LLM 一律經 ``backend.core.llm.call_llm``。
- ``no_orchestrator_bypass``（C-SEAT-005，P0）：插件／模組層（``backend/modules/``）
  與業務層（``backend/linkin/``）禁止繞過協調器直連 L2 執行席。

用法：``python -m backend.scripts.lint_contracts [root]``；違規時 exit 1。
測試可呼叫 ``scan(root)`` 取得違規清單（可 monkeypatch，不需真實 CI）。
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

# ── C-LLM-001：供應商 SDK 直連掃描 ─────────────────────────────
_PROVIDER_SDK = re.compile(
    r"^\s*(?:from|import)\s+("
    r"openai|anthropic|litellm|google\.generativeai|dashscope|zhipuai|volcengine"
    r")(?:\.\w+)?(?:\s+import|\s*$)",
    re.MULTILINE,
)

# 允許直連 SDK 的路徑（LLM 調用層／嵌入層／測試）；其餘一律違規
_SDK_ALLOWLIST: tuple[str, ...] = (
    "backend/core/llm.py",          # 唯一 LLM 調用層（AGENTS.md 關鍵約束 #1）
    "backend/core/api_router.py",   # 多 API 路由（call_llm 底層）
    "backend/core/llm_cache.py",    # LLM 快取層（call_llm 底層）
    "backend/memory/vector_store.py",  # litellm.embedding（嵌入層，非生成）
    "backend/scripts/test_llm_connection.py",
)

# ── C-SEAT-005：繞過指揮鏈掃描 ─────────────────────────────────
# 插件／模組層與業務層不得直連 L2 執行席；工作項只經協調器下發（§2.3）
_BYPASS_IMPORT = re.compile(
    r"^\s*from\s+backend\.company\.raho\.atomic_executor\s+import",
    re.MULTILINE,
)
_BYPASS_SCOPES: tuple[str, ...] = ("backend/modules/", "backend/linkin/")


@dataclass(frozen=True)
class Violation:
    rule: str          # lint 規則 ID（對齊 runtime.md「驗證」欄）
    path: str
    line: int
    excerpt: str

    def __str__(self) -> str:
        return f"[{self.rule}] {self.path}:{self.line}: {self.excerpt.strip()}"


def _norm(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _iter_py(root: Path):
    yield from sorted(root.rglob("*.py"))


def scan_file(path: Path, root: Path) -> list[Violation]:
    rel = _norm(path, root)
    if "/tests/" in f"/{rel}" or rel.startswith("backend/tests/"):
        return []  # 測試碼可自由 stub／monkeypatch
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    out: list[Violation] = []
    if rel not in _SDK_ALLOWLIST:
        for match in _PROVIDER_SDK.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            out.append(Violation("no_direct_provider_sdk", rel, line, match.group(0)))
    if any(rel.startswith(scope) for scope in _BYPASS_SCOPES):
        for match in _BYPASS_IMPORT.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            out.append(Violation("no_orchestrator_bypass", rel, line, match.group(0)))
    return out


def scan(root: str | Path = ".") -> list[Violation]:
    root_path = Path(root)
    violations: list[Violation] = []
    for path in _iter_py(root_path / "backend"):
        violations.extend(scan_file(path, root_path))
    return violations


def main(argv: list[str] | None = None) -> int:
    root = (argv or sys.argv[1:] or ["."])[0]
    violations = scan(root)
    for v in violations:
        print(v)
    if violations:
        print(f"\n契約 lint 失敗：{len(violations)} 處違規（C-LLM-001／C-SEAT-005）")
        return 1
    print("契約 lint 通過：無直連 SDK／無繞過指揮鏈")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
