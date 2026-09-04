"""架构约束测试（AGENTS.md 禁止条款的机械覆盖）。

验证两条架构护栏：
1. 节点模块（nodes.py / company_nodes.py / company/）不得直接导入
   供应商 SDK（openai / anthropic 等），LLM 调用仅经
   backend.core.llm.call_llm
2. evoloop_graph 由 build_graph() 产生，无模块直接修改图状态
"""

import ast
import os
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# ── 供应商 SDK 模块名（禁止在节点模块中直接导入） ──
FORBIDDEN_VENDOR_SDKS: set[str] = {
    "openai",
    "anthropic",
    "cohere",
    "boto3",            # AWS Bedrock
    "replicate",
    "together",
    "google.generativeai",
    "ai21",
    "aleph_alpha",
    "mistralai",
}

# ── 需要检查的节点模块文件路径 ──
NODE_MODULE_FILES: list[str] = [
    "backend/core/nodes.py",
    "backend/core/company_nodes.py",
    "backend/linkin/pipeline.py",
]

# ── evoloop_graph 定义所在文件 ──
GRAPH_FILE = "backend/core/graph.py"

# ── evoloop_graph 上的变异方法（禁止在其他模块中调用） ──
MUTATING_METHODS: set[str] = {
    "add_node",
    "add_edge",
    "add_conditional_edges",
    "set_entry_point",
    "set_finish_point",
    "compile",
    "set_conditional_entry_point",
}


# ═══════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════

def _collect_python_files(root_dir: Path) -> list[Path]:
    """递归收集目录下所有 .py 文件（排除 __pycache__ 和 tests）。"""
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [d for d in dirnames if d not in ("__pycache__", "tests")]
        for fname in filenames:
            if fname.endswith(".py"):
                files.append(Path(dirpath) / fname)
    return files


def _iter_forbidden_imports(tree: ast.AST) -> list[str]:
    """遍历 AST 收集所有被禁止的厂商 SDK 导入语句。

    返回格式如 ["import openai", "from anthropic import ..."] 的列表。
    """
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name.split(".")[0]
                if name in FORBIDDEN_VENDOR_SDKS:
                    violations.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            name = node.module.split(".")[0]
            if name in FORBIDDEN_VENDOR_SDKS:
                names = ", ".join(a.name for a in node.names)
                violations.append(f"from {node.module} import {names}")
    return violations


def _iter_evoloop_graph_mutations(tree: ast.AST) -> list[str]:
    """遍历 AST 收集所有对 evoloop_graph 的变异调用。

    返回格式如 ["evoloop_graph.add_node(...) at line 42"] 的列表。
    """
    violations: list[str] = []
    for node in ast.walk(tree):
        # 匹配 evoloop_graph.<method>(...) 形式
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                if func.value.id == "evoloop_graph" and func.attr in MUTATING_METHODS:
                    violations.append(
                        f"evoloop_graph.{func.attr}(...) at line {node.lineno}"
                    )
    return violations


def _parse_file(filepath: Path) -> ast.AST:
    """稳健解析 Python 文件为 AST，解析失败时抛出带有文件路径的异常。"""
    source = filepath.read_text(encoding="utf-8")
    try:
        return ast.parse(source, filename=str(filepath))
    except SyntaxError as exc:
        raise AssertionError(
            f"无法解析 {filepath}：{exc}"
        ) from exc


# ═══════════════════════════════════════════════════════════════
# 约束 1：节点模块不得导入供应商 SDK
# ═══════════════════════════════════════════════════════════════

class TestLLMArchitectureConstraint:
    """验证 LLM 调用架构约束。

    - 节点模块不得直接导入 openai / anthropic 等供应商 SDK
    - 节点模块中若存在 LLM 调用，必须通过 backend.core.llm.call_llm
    """

    @pytest.mark.parametrize(
        "rel_path",
        NODE_MODULE_FILES,
    )
    def test_node_module_no_vendor_sdk_import(self, rel_path: str):
        """backend/core/nodes.py 与 backend/core/company_nodes.py
        不导入任何供应商 SDK。"""
        filepath = PROJECT_ROOT / rel_path
        assert filepath.exists(), f"文件不存在：{filepath}"
        tree = _parse_file(filepath)
        violations = _iter_forbidden_imports(tree)
        assert not violations, (
            f"{rel_path} 包含禁止的供应商 SDK 导入：\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    def test_company_modules_no_vendor_sdk_import(self):
        """backend/company/ 下所有 Python 模块不导入任何供应商 SDK。"""
        company_dir = PROJECT_ROOT / "backend" / "company"
        if not company_dir.exists():
            pytest.skip("backend/company/ 目录不存在")
        py_files = _collect_python_files(company_dir)
        all_violations: dict[str, list[str]] = {}
        for py_file in py_files:
            tree = _parse_file(py_file)
            v = _iter_forbidden_imports(tree)
            if v:
                rel = str(py_file.relative_to(PROJECT_ROOT))
                all_violations[rel] = v
        assert not all_violations, (
            "backend/company/ 模块包含禁止的供应商 SDK 导入：\n"
            + "\n".join(
                f"  {f}：{', '.join(vs)}" for f, vs in all_violations.items()
            )
        )

    def test_core_nodes_no_direct_litellm_import(self):
        """backend/core/nodes.py 与 company_nodes.py 不直接导入 litellm。

        litellm 的导入应仅限于 backend/core/llm.py（LLM 抽象层）
        和 backend/memory/vector_store.py（嵌入向量）。
        """
        for rel_path in NODE_MODULE_FILES:
            filepath = PROJECT_ROOT / rel_path
            tree = _parse_file(filepath)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith("litellm"):
                            raise AssertionError(
                                f"{rel_path} 直接 import litellm，"
                                f"应通过 backend.core.llm.call_llm 调用"
                            )
                elif isinstance(node, ast.ImportFrom):
                    if node.module and node.module.startswith("litellm"):
                        raise AssertionError(
                            f"{rel_path} 直接 from litellm import ...，"
                            f"应通过 backend.core.llm.call_llm 调用"
                        )

    def test_company_modules_no_direct_litellm_import(self):
        """backend/company/ 下模块不直接导入 litellm。"""
        company_dir = PROJECT_ROOT / "backend" / "company"
        if not company_dir.exists():
            pytest.skip("backend/company/ 目录不存在")
        py_files = _collect_python_files(company_dir)
        for py_file in py_files:
            tree = _parse_file(py_file)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith("litellm"):
                            rel = str(py_file.relative_to(PROJECT_ROOT))
                            raise AssertionError(
                                f"{rel} 直接 import litellm，"
                                f"应通过 backend.core.llm.call_llm 调用"
                            )
                elif isinstance(node, ast.ImportFrom):
                    if node.module and node.module.startswith("litellm"):
                        rel = str(py_file.relative_to(PROJECT_ROOT))
                        raise AssertionError(
                            f"{rel} 直接 from litellm import ...，"
                            f"应通过 backend.core.llm.call_llm 调用"
                        )

    def test_hub_modules_no_vendor_sdk_or_litellm(self):
        """backend/hub/ 不得直连厂商 SDK 或 litellm，只经 call_llm。"""
        hub_dir = PROJECT_ROOT / "backend" / "hub"
        assert hub_dir.exists(), "backend/hub/ 目录不存在"
        py_files = _collect_python_files(hub_dir)
        assert py_files, "backend/hub/ 没有 Python 文件"
        for py_file in py_files:
            tree = _parse_file(py_file)
            violations = _iter_forbidden_imports(tree)
            assert not violations, (
                f"{py_file.relative_to(PROJECT_ROOT)} 包含禁止的供应商 SDK 导入："
                + ", ".join(violations)
            )
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith("litellm"):
                            raise AssertionError(
                                f"{py_file.relative_to(PROJECT_ROOT)} 直接 import litellm"
                            )
                elif isinstance(node, ast.ImportFrom):
                    if node.module and node.module.startswith("litellm"):
                        raise AssertionError(
                            f"{py_file.relative_to(PROJECT_ROOT)} 直接 from litellm import"
                        )


# ═══════════════════════════════════════════════════════════════
# 约束 2：evoloop_graph 由 build_graph() 产生，不可直接修改
# ═══════════════════════════════════════════════════════════════

class TestGraphArchitectureConstraint:
    """验证 LangGraph 图状态架构约束。

    - evoloop_graph 必须由 build_graph() 函数产生
    - 无模块直接调用 evoloop_graph 上的变异方法
    """

    def test_evoloop_graph_assigned_from_build_graph(self):
        """验证 evoloop_graph 的赋值来源是 build_graph() 调用。"""
        filepath = PROJECT_ROOT / GRAPH_FILE
        tree = _parse_file(filepath)

        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "evoloop_graph":
                        found = True
                        # 赋值右侧必须是 build_graph() 调用
                        assert isinstance(node.value, ast.Call), (
                            f"evoloop_graph 赋值右侧不是函数调用，"
                            f"当前为 {ast.dump(node.value)[:120]}"
                        )
                        func = node.value.func
                        if isinstance(func, ast.Name):
                            assert func.id == "build_graph", (
                                f"evoloop_graph 应由 build_graph() 产生，"
                                f"当前调用 {func.id}()"
                            )
                        elif isinstance(func, ast.Attribute):
                            assert func.attr == "build_graph", (
                                f"evoloop_graph 应由 build_graph() 产生，"
                                f"当前调用 {func.attr}()"
                            )
                        else:
                            raise AssertionError(
                                "evoloop_graph 赋值右侧不是 build_graph() 调用"
                            )
        assert found, (
            f"{GRAPH_FILE} 中未找到 evoloop_graph 的赋值语句"
        )

    def test_no_other_module_assigns_evoloop_graph(self):
        """验证除 graph.py 外，无其他模块对 evoloop_graph 赋值。"""
        backend_dir = PROJECT_ROOT / "backend"
        all_py: list[Path] = []
        for dirpath, dirnames, filenames in os.walk(backend_dir):
            dirnames[:] = [d for d in dirnames if d not in ("__pycache__",)]
            for fname in filenames:
                if fname.endswith(".py"):
                    all_py.append(Path(dirpath) / fname)

        violations: list[str] = []
        for py_file in all_py:
            if py_file.name == "graph.py" and py_file.parent.name == "core":
                continue  # 跳过 graph.py 本身
            source = py_file.read_text(encoding="utf-8")
            if "evoloop_graph" not in source:
                continue
            tree = _parse_file(py_file)
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == "evoloop_graph":
                            rel = str(py_file.relative_to(PROJECT_ROOT))
                            violations.append(
                                f"{rel} line {node.lineno}：对 evoloop_graph 赋值"
                            )
                elif isinstance(node, ast.AnnAssign):
                    target = node.target
                    if isinstance(target, ast.Name) and target.id == "evoloop_graph":
                        rel = str(py_file.relative_to(PROJECT_ROOT))
                        violations.append(
                            f"{rel} line {node.lineno}：对 evoloop_graph 类型注解赋值"
                        )
        assert not violations, (
            "除 graph.py 外，以下模块对 evoloop_graph 进行了赋值：\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    def test_no_module_directly_mutates_evoloop_graph(self):
        """验证除 graph.py 外，无模块调用 evoloop_graph 的变异方法。

        变异方法包括：add_node, add_edge, add_conditional_edges,
        set_entry_point, set_finish_point, compile 等。
        """
        backend_dir = PROJECT_ROOT / "backend"
        all_py: list[Path] = []
        for dirpath, dirnames, filenames in os.walk(backend_dir):
            dirnames[:] = [d for d in dirnames if d not in ("__pycache__",)]
            for fname in filenames:
                if fname.endswith(".py"):
                    all_py.append(Path(dirpath) / fname)

        all_violations: dict[str, list[str]] = {}
        for py_file in all_py:
            if py_file.name == "graph.py" and py_file.parent.name == "core":
                continue  # graph.py 内部调用是允许的（build_graph 中）
            source = py_file.read_text(encoding="utf-8")
            if "evoloop_graph" not in source:
                continue
            tree = _parse_file(py_file)
            mutations = _iter_evoloop_graph_mutations(tree)
            if mutations:
                rel = str(py_file.relative_to(PROJECT_ROOT))
                all_violations[rel] = mutations

        assert not all_violations, (
            "以下模块直接调用了 evoloop_graph 的变异方法：\n"
            + "\n".join(
                f"  {f}：\n    " + "\n    ".join(vs)
                for f, vs in all_violations.items()
            )
            + "\n\n所有图变更应通过修改 build_graph() 函数完成。"
        )