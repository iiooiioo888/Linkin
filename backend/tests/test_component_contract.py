"""組件契約測試（B0：契約 + 安全網，零行為變更）。

三類斷言：

1. **契約自身**：id、依賴、surface/nav 對應、寫入護欄、kind 分類。
2. **重構安全網**：路由集合、OpenAPI、字面/參數遮蔽、既有 `/modules` 輸出。
3. **測試 patch 面**：``backend.main`` 的 re-export 與 patch 目標仍然存在。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROUTE_PARITY_PATH = PROJECT_ROOT / "docs" / "contracts" / "component-route-parity.json"
OPENAPI_SNAPSHOT_PATH = PROJECT_ROOT / "docs" / "contracts" / "openapi-snapshot.json"
MANIFEST_PATHS = (
    PROJECT_ROOT / "frontend" / "src" / "generated" / "component-manifest.json",
    PROJECT_ROOT / "docs" / "contracts" / "component-manifest.json",
)

_KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


@pytest.fixture()
def components():
    from backend.modules.component_registry import get_builtin_components

    return get_builtin_components()


# ═══════════════════════════════════════════════════════════════
# 1. 契約自身
# ═══════════════════════════════════════════════════════════════


def test_component_ids_are_unique_and_kebab_case(components):
    ids = [spec.id for spec in components]
    assert len(ids) == len(set(ids)), f"組件 id 重複：{ids}"
    for spec in components:
        assert _KEBAB_RE.match(spec.id), f"組件 id 非 kebab-case：{spec.id}"
        assert spec.title, f"組件 {spec.id} 缺 title"


def test_component_requires_are_satisfied_and_acyclic(components):
    from backend.modules.component_registry import resolve_order

    ids = {spec.id for spec in components}
    for spec in components:
        missing = [dep for dep in spec.requires if dep not in ids]
        assert not missing, f"組件 {spec.id} 宣告了不存在的依賴：{missing}"
    # 成環會拋 ComponentDependencyError
    assert len(resolve_order(list(components))) == len(components)


def test_surfaces_reference_existing_nav_and_capabilities(components):
    for spec in components:
        nav_ids = {group.id for group in spec.nav_groups}
        cap_ids = {cap.id for cap in spec.capabilities}
        keys = [surface.key for surface in spec.surfaces]
        assert len(keys) == len(set(keys)), f"組件 {spec.id} 的 surface key 重複：{keys}"
        for surface in spec.surfaces:
            if surface.nav_group:
                assert surface.nav_group in nav_ids, (
                    f"組件 {spec.id} 的 surface {surface.key} 指向不存在的 nav_group "
                    f"{surface.nav_group}"
                )
            if surface.capability:
                assert surface.capability in cap_ids, (
                    f"組件 {spec.id} 的 surface {surface.key} 指向不存在的 capability "
                    f"{surface.capability}"
                )


def test_write_capabilities_declare_guards(components):
    for spec in components:
        if spec.write_capabilities():
            assert spec.guards, (
                f"組件 {spec.id} 有 write=True 的能力 "
                f"{[c.id for c in spec.write_capabilities()]} 但未宣告任何 GuardRequirement"
            )


def test_guard_enforced_by_points_at_existing_module(components):
    """護欄必須落在既有強制點，不得自造旁路。"""
    import importlib

    for spec in components:
        for guard in spec.guards:
            assert guard.enforced_by, f"組件 {spec.id} 的護欄 {guard.kind} 缺 enforced_by"
            module_path = guard.enforced_by.split(":")[0]
            # 允許指向模組內的屬性（backend.x.y.attr），逐段縮短找到可 import 的模組
            parts = module_path.split(".")
            imported = False
            for end in range(len(parts), 2, -1):
                try:
                    importlib.import_module(".".join(parts[:end]))
                except ImportError:
                    continue
                imported = True
                break
            assert imported, f"組件 {spec.id} 的護欄指向不存在的模組：{guard.enforced_by}"


def test_integration_components_use_known_sections(components):
    from backend.modules.component import INTEGRATION_SECTIONS

    for spec in components:
        if spec.kind != "integration":
            continue
        for group in spec.nav_groups:
            if group.area != "lab":
                continue
            assert group.id in INTEGRATION_SECTIONS, (
                f"整合類組件 {spec.id} 的 lab 分組 {group.id} 不在六個功能 id 內："
                f"{INTEGRATION_SECTIONS}"
            )


def test_kind_is_known(components):
    allowed = {"core", "price", "integration", "world"}
    for spec in components:
        assert spec.kind in allowed, f"組件 {spec.id} 的 kind 未知：{spec.kind}"


# ═══════════════════════════════════════════════════════════════
# 2. 重構安全網
# ═══════════════════════════════════════════════════════════════


def test_route_set_matches_baseline():
    """路由集合必須與 master 基準完全相同（不刪、不改路徑、不改方法）。

    只比集合不比順序：元件化收編後全域順序必然改變（各功能聚成一塊），
    順序安全性另由 ``test_literal_param_shadowing`` 守。
    """
    from backend.main import app
    from backend.scripts.route_table import flatten_routes

    baseline = json.loads(ROUTE_PARITY_PATH.read_text(encoding="utf-8"))
    expected = {
        (row["path"], tuple(sorted(row["methods"])), row["name"])
        for row in baseline["routes"]
    }
    actual = {(entry.path, entry.methods, entry.name) for entry in flatten_routes(app.routes)}

    assert actual - expected == set(), f"出現基準沒有的路由：{sorted(actual - expected)[:10]}"
    assert expected - actual == set(), f"基準路由消失：{sorted(expected - actual)[:10]}"


def test_route_count_matches_baseline():
    from backend.main import app
    from backend.scripts.route_table import flatten_routes

    baseline = json.loads(ROUTE_PARITY_PATH.read_text(encoding="utf-8"))
    assert len(flatten_routes(app.routes)) == baseline["count"]


def test_literal_param_shadowing():
    """同 method、同深度下若有字面路徑與參數路徑僅差在參數段，
    字面路徑必須宣告在前，否則 FastAPI 永遠匹配不到它。

    B0 基準只有一組：``/plugins/catalog`` vs ``/plugins/{plugin_id}``。
    """
    from backend.main import app
    from backend.scripts.route_table import flatten_routes

    entries = flatten_routes(app.routes)
    by_method_depth: dict[tuple[str, int], list[tuple[int, str]]] = {}
    for position, entry in enumerate(entries):
        segments = [s for s in entry.path.split("/") if s]
        for method in entry.methods:
            by_method_depth.setdefault((method, len(segments)), []).append((position, entry.path))

    def shadow_pairs(rows: list[tuple[int, str]]):
        for i, (pos_a, path_a) in enumerate(rows):
            seg_a = [s for s in path_a.split("/") if s]
            for pos_b, path_b in rows[i + 1 :]:
                seg_b = [s for s in path_b.split("/") if s]
                if seg_a == seg_b:
                    continue
                if all(a == b or (a.startswith("{") != b.startswith("{")) for a, b in zip(seg_a, seg_b)):
                    yield pos_a, path_a, pos_b, path_b

    violations = []
    for (method, _depth), rows in by_method_depth.items():
        for pos_literal, literal, pos_param, param in shadow_pairs(rows):
            # 判定哪條是「字面」：段內無大括號者
            if "{" in literal:
                continue
            if pos_literal > pos_param:
                violations.append((method, literal, param))
    assert not violations, f"字面路由被參數路由遮蔽：{violations}"


def test_openapi_snapshot_unchanged():
    """OpenAPI 路徑與 operation 數不得漂移（比對 schema 全等）。"""
    from backend.scripts.export_openapi_snapshot import build_payload

    snapshot = json.loads(OPENAPI_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    current = build_payload()
    assert current["path_count"] == snapshot["path_count"]
    assert current["paths"] == snapshot["paths"], "OpenAPI paths 已漂移"
    assert current["components"] == snapshot["components"], "OpenAPI components 已漂移"


def test_modules_catalog_output_unchanged():
    """``GET /modules`` 的輸出必須與收編前一致（順序敏感）。"""
    from backend.modules.local_video_studio import build_local_video_studio_spec
    from backend.modules.local_video_studio_component import build_component as lvs
    from backend.modules.media_vault import build_media_vault_spec
    from backend.modules.media_vault_component import build_component as mv

    assert build_media_vault_spec().to_dict() == mv().to_module_spec().to_dict()
    assert build_local_video_studio_spec().to_dict() == lvs().to_module_spec().to_dict()


def test_builtin_component_order_matches_catalog_expectation():
    """投影順序決定 ``GET /modules`` 的順序；既有測試斷言 media-vault 在前。"""
    from backend.modules.component_registry import get_builtin_components

    ids = [spec.id for spec in get_builtin_components() if spec.is_catalog_exposed()]
    assert ids == ["media-vault", "local-video-studio"]


def test_manifest_in_sync():
    """manifest 必須與程式內容一致（純函式重算比對，不落盤）。"""
    from backend.scripts.export_component_manifest import build_payload, dumps

    expected = dumps(build_payload())
    for path in MANIFEST_PATHS:
        assert path.exists(), f"缺少 manifest：{path}"
        assert path.read_text(encoding="utf-8") == expected, f"manifest 已漂移：{path}"


def test_manifest_schema():
    payload = json.loads(MANIFEST_PATHS[0].read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    for item in payload["components"]:
        assert item["id"]
        assert item["gateway_prefix"] == f"/modules/{item['id']}/api"
        assert item["status"] in {"installed", "enabled", "disabled", "degraded"}


def test_api_reference_paths_exist():
    """``docs/api/reference.md`` 列出的路徑都必須真的存在。

    文件可能寫成 ``/cloud/monitoring?range=1h``（帶 query），比對前剝除 query。
    """
    from backend.main import app
    from backend.scripts.route_table import flatten_routes

    reference = (PROJECT_ROOT / "docs" / "api" / "reference.md").read_text(encoding="utf-8")
    documented = {
        path.split("?")[0]
        for path in re.findall(r"^###\s+(?:GET|POST|PUT|PATCH|DELETE)\s+(/\S*)", reference, re.MULTILINE)
    }
    if not documented:
        pytest.skip("reference.md 無可解析端點")
    available = {entry.path for entry in flatten_routes(app.routes)}
    missing = sorted(documented - available)
    assert not missing, f"reference.md 記錄了不存在的路徑：{missing}"


# ═══════════════════════════════════════════════════════════════
# 3. 測試 patch 面（monkeypatch 位移防線）
# ═══════════════════════════════════════════════════════════════


def test_main_reexports_exist():
    """``backend.main`` 必須保留測試 patch 用的名字（見計畫 §4.4）。"""
    import backend.main as main_module

    for name in ("call_llm", "call_llm_stream", "nodes", "task_manager", "update_company_budget_state"):
        assert hasattr(main_module, name), f"backend.main 缺少 re-export：{name}"


def test_task_manager_patch_is_live(monkeypatch):
    """patch ``backend.main.task_manager`` 必須真的換掉端點看到的物件。

    這是「假綠」防線：若 handler 改成從新模組取 ``task_manager``，
    這裡把模組級名字換成哨兵後，handler 的 global 查找就會拿到哨兵。
    做法不經 TestClient（避免觸發 lifespan 的 ``task_manager._loop``），
    直接檢查 handler 的 ``__globals__`` 是否就是 ``backend.main`` 的命名空間。
    """
    import backend.main as main_module

    sentinel = object()
    monkeypatch.setattr(main_module, "task_manager", sentinel)

    handler = next(
        route.endpoint
        for route in main_module.app.routes
        if getattr(route, "path", None) == "/tasks/{task_id}" and hasattr(route, "endpoint")
    )
    assert handler.__globals__.get("task_manager") is sentinel, (
        "「/tasks/{task_id}」的 handler 已不從 backend.main 取 task_manager——"
        "搬遷時必須同步更新 backend/tests/test_multitenant_roles.py 的 patch 路徑"
    )
