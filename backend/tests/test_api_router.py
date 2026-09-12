"""多 API 路由：千問／DeepSeek／Kimi／OpenRouter 並存與角色級模型鎖定。"""

from __future__ import annotations

from backend.core.api_router import (
    find_route_for_model,
    list_failover_chain,
    list_routes,
    normalize_route,
    public_router_state,
    reset_router_state,
    resolve_route_ref,
    resolve_target,
    save_routes,
    select_route,
    set_route_strategy,
    union_allowed_models,
    upsert_route,
)
from backend.core.llm import _truncate_prompt, llm_kwargs_for_role
from backend.core.llm_config import save_runtime_config
from backend.core.provider_pool import TOKEN_PLAN_LABEL, clamp_model, refresh_model_catalog
from backend.services.task_manager import task_manager


def test_single_config_still_synthesizes_primary(monkeypatch):
    save_runtime_config(
        api_key="sk-ds-only",
        api_base="https://api.deepseek.com",
        model="deepseek-v4-flash",
    )
    monkeypatch.setattr(
        "backend.core.provider_pool._http_get_json",
        lambda url, key, timeout=15.0: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    refresh_model_catalog(reason="test")
    routes = list_routes()
    assert any(r["provider"] == "deepseek" for r in routes)
    assert clamp_model("gpt-4o") == "deepseek-v4-flash"


def test_multi_route_clamp_keeps_qwen_and_deepseek(monkeypatch):
    monkeypatch.setattr(
        "backend.core.provider_pool._http_get_json",
        lambda url, key, timeout=15.0: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    save_routes(
        [
            {
                "id": "deepseek",
                "provider": "deepseek",
                "api_key": "sk-ds",
                "api_base": "https://api.deepseek.com",
                "model": "deepseek-v4-flash",
                "weight": 30,
                "is_default": True,
            },
            {
                "id": "qwen",
                "provider": "qwen",
                "api_key": "sk-qwen",
                "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "model": "qwen-plus",
                "weight": 40,
            },
        ]
    )
    assert clamp_model("qwen-max") == "qwen-max"
    assert clamp_model("deepseek-v4-pro") == "deepseek-v4-pro"
    assert clamp_model("gpt-4o") == "deepseek-v4-flash"
    owned = find_route_for_model("qwen-plus")
    assert owned is not None and owned["id"] == "qwen"
    union = union_allowed_models()
    assert "qwen-plus" in union
    assert "deepseek-v4-flash" in union


def test_resolve_target_uses_role_provider():
    save_routes(
        [
            {
                "id": "qwen",
                "provider": "qwen",
                "api_key": "sk-qwen-role",
                "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "model": "qwen-plus",
                "is_default": False,
            },
            {
                "id": "deepseek",
                "provider": "deepseek",
                "api_key": "sk-ds-role",
                "api_base": "https://api.deepseek.com",
                "model": "deepseek-v4-flash",
                "is_default": True,
            },
        ]
    )
    target = resolve_target(model="qwen-max", route_id="qwen")
    assert target["route_id"] == "qwen"
    assert target["api_key"] == "sk-qwen-role"
    assert target["model"] == "qwen-max"
    default = resolve_target()
    assert default["route_id"] == "deepseek"


def test_weighted_round_robin_spreads(monkeypatch):
    reset_router_state()
    save_routes(
        [
            {
                "id": "a",
                "provider": "deepseek",
                "api_key": "sk-a",
                "api_base": "https://api.deepseek.com",
                "model": "deepseek-v4-flash",
                "weight": 70,
                "enabled": True,
            },
            {
                "id": "b",
                "provider": "qwen",
                "api_key": "sk-b",
                "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "model": "qwen-plus",
                "weight": 30,
                "enabled": True,
            },
        ],
        strategy="weighted_round_robin",
    )
    set_route_strategy("weighted_round_robin")
    counts = {"a": 0, "b": 0}
    for _ in range(100):
        route = select_route(strategy="weighted_round_robin")
        assert route is not None
        counts[route["id"]] += 1
    assert counts["a"] > counts["b"]
    assert counts["b"] > 0


def test_role_runtime_clamps_to_chosen_provider(monkeypatch):
    from backend.company.role_catalog import create_custom_role, resolve_runtime

    monkeypatch.setattr(
        "backend.core.provider_pool._http_get_json",
        lambda url, key, timeout=15.0: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    save_routes(
        [
            {
                "id": "deepseek",
                "provider": "deepseek",
                "api_key": "sk-ds",
                "api_base": "https://api.deepseek.com",
                "model": "deepseek-v4-flash",
                "is_default": True,
            },
            {
                "id": "qwen",
                "provider": "qwen",
                "api_key": "sk-qwen",
                "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "model": "qwen-plus",
            },
        ]
    )
    created = create_custom_role(
        {
            "id": "api_split_coder",
            "name": "split coder",
            "preferred_provider": "qwen",
            "preferred_model": "qwen-max",
            "max_output_tokens": 2048,
            "context_window": 8000,
            "system_prompt": "test",
        }
    )
    runtime = resolve_runtime(created["id"])
    assert runtime["preferred_provider"] == "qwen"
    assert runtime["preferred_model"] == "qwen-max"
    kwargs = llm_kwargs_for_role(runtime)
    assert kwargs["route_id"] == "qwen"
    assert kwargs["max_tokens"] == 2048
    assert kwargs["max_context_tokens"] == 8000


def test_truncate_prompt_respects_token_budget():
    text = "abcd" * 80
    out = _truncate_prompt(text, max_context_tokens=10)
    assert len(out) < len(text)
    assert "..." in out or "token" in out.lower() or len(out) <= 80


def test_routes_http_crud(monkeypatch):
    from fastapi.testclient import TestClient

    from backend.main import app

    monkeypatch.setattr(task_manager, "tasks", {})
    monkeypatch.setattr(
        "backend.core.provider_pool._http_get_json",
        lambda url, key, timeout=15.0: {"data": [{"id": "qwen-plus"}, {"id": "qwen-max"}]},
    )

    with TestClient(app) as client:
        created = client.post(
            "/config/routes",
            json={
                "id": "qwen",
                "provider": "qwen",
                "api_key": "sk-qwen-http",
                "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "model": "qwen-plus",
                "weight": 40,
                "is_default": True,
            },
        )
        assert created.status_code == 200, created.text
        body = created.json()
        ids = {r["id"] for r in body["api_routes"]}
        assert "qwen" in ids
        listed = client.get("/config/routes")
        assert listed.status_code == 200
        assert listed.json()["route_strategy"]
        cfg = client.get("/config")
        assert cfg.status_code == 200
        assert cfg.json()["api_routes"]
        catalog = client.get("/monitor/agents")
        assert catalog.status_code == 200
        meta = catalog.json()["catalog_meta"]
        assert meta["api_routes"]
        assert meta["models_by_provider"]
        assert meta["model_token_hints"]["qwen-max"]["max_output"] > 0


def test_failover_selects_default_then_fallback():
    reset_router_state()
    save_routes(
        [
            {
                "id": "qwen",
                "provider": "qwen",
                "api_key": "sk-qwen-fb",
                "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "model": "qwen-plus",
                "fallback": True,
                "is_default": False,
            },
            {
                "id": "deepseek",
                "provider": "deepseek",
                "api_key": "sk-ds-main",
                "api_base": "https://api.deepseek.com",
                "model": "deepseek-v4-flash",
                "is_default": True,
            },
        ],
        strategy="failover",
        default_id="deepseek",
    )
    set_route_strategy("failover")
    route = select_route(strategy="failover")
    assert route is not None and route["id"] == "deepseek"
    chain = list_failover_chain()
    assert chain[0]["id"] == "deepseek"
    assert any(r["id"] == "qwen" for r in chain[1:])


def test_resolve_route_ref_by_provider_kind():
    save_routes(
        [
            {
                "id": "company-qwen",
                "provider": "qwen",
                "api_key": "sk-qwen-kind",
                "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "model": "qwen-plus",
            },
            {
                "id": "deepseek",
                "provider": "deepseek",
                "api_key": "sk-ds-kind",
                "api_base": "https://api.deepseek.com",
                "model": "deepseek-v4-flash",
                "is_default": True,
            },
        ]
    )
    hit = resolve_route_ref("qwen")
    assert hit is not None and hit["id"] == "company-qwen"
    kwargs = llm_kwargs_for_role(
        {
            "preferred_provider": "qwen",
            "preferred_model": "qwen-max",
            "max_output_tokens": 1024,
            "context_window": 8000,
        }
    )
    assert kwargs["route_id"] == "company-qwen"
    assert kwargs["max_tokens"] == 1024
    assert kwargs["max_context_tokens"] == 8000


def test_call_llm_cross_route_failover(monkeypatch):
    from backend.core import llm as llm_mod

    save_routes(
        [
            {
                "id": "deepseek",
                "provider": "deepseek",
                "api_key": "sk-ds-fail",
                "api_base": "https://api.deepseek.com",
                "model": "deepseek-v4-flash",
                "is_default": True,
            },
            {
                "id": "qwen",
                "provider": "qwen",
                "api_key": "sk-qwen-ok",
                "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "model": "qwen-plus",
                "fallback": True,
            },
        ],
        strategy="failover",
        default_id="deepseek",
    )
    set_route_strategy("failover")
    seen: list[str] = []

    def fake_once(prompt, system=None, model=None, max_retries=None, *, route_id=None, max_context_tokens=None, **kwargs):
        seen.append(str(route_id or ""))
        if route_id == "deepseek":
            raise RuntimeError("ds down")
        return "ok-from-qwen"

    class _Cache:
        def get(self, *args, **kwargs):
            return None

        def put(self, *args, **kwargs):
            return None

    monkeypatch.setattr(llm_mod, "pool_failover_enabled", lambda: False)
    monkeypatch.setattr(llm_mod, "get_llm_cache", lambda: _Cache())
    monkeypatch.setattr(llm_mod, "_completion_once", fake_once)
    text = llm_mod.call_llm("hi")
    assert text == "ok-from-qwen"
    assert "deepseek" in seen
    assert "qwen" in seen


def test_locked_models_survive_refresh(monkeypatch):
    from backend.core.api_router import get_route
    from backend.core.provider_pool import refresh_route_catalog

    monkeypatch.setattr(
        "backend.core.provider_pool._http_get_json",
        lambda url, key, timeout=15.0: {
            "data": [{"id": "qwen-plus"}, {"id": "qwen-max"}, {"id": "qwen-turbo"}]
        },
    )
    upsert_route(
        {
            "id": "qwen",
            "provider": "qwen",
            "api_key": "sk-qwen-lock",
            "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "model": "qwen-plus",
            "allowed_models": ["qwen-plus", "qwen-max"],
            "models_locked": True,
            "is_default": True,
        }
    )
    refresh_route_catalog("qwen", reason="test")
    route = get_route("qwen")
    assert route is not None
    assert set(route["allowed_models"]) == {"qwen-plus", "qwen-max"}
    assert route["models_locked"] is True
    assert "qwen-turbo" not in route["allowed_models"]


def test_wrr_splits_even_when_model_belongs_to_one_route():
    reset_router_state()
    save_routes(
        [
            {
                "id": "deepseek",
                "provider": "deepseek",
                "api_key": "sk-ds-wrr",
                "api_base": "https://api.deepseek.com",
                "model": "deepseek-v4-flash",
                "weight": 50,
                "is_default": True,
            },
            {
                "id": "qwen",
                "provider": "qwen",
                "api_key": "sk-qwen-wrr",
                "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "model": "qwen-plus",
                "weight": 50,
            },
        ],
        strategy="weighted_round_robin",
    )
    set_route_strategy("weighted_round_robin")
    seen: set[str] = set()
    for _ in range(20):
        route = select_route(model="qwen-plus", strategy="weighted_round_robin")
        assert route is not None
        seen.add(route["id"])
    assert seen == {"deepseek", "qwen"}


def test_least_loaded_prefers_idle_route():
    from backend.core.api_router import mark_route_end, mark_route_start

    reset_router_state()
    save_routes(
        [
            {
                "id": "busy",
                "provider": "deepseek",
                "api_key": "sk-busy",
                "api_base": "https://api.deepseek.com",
                "model": "deepseek-v4-flash",
                "weight": 10,
                "is_default": True,
            },
            {
                "id": "idle",
                "provider": "qwen",
                "api_key": "sk-idle",
                "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "model": "qwen-plus",
                "weight": 10,
            },
        ],
        strategy="least_loaded",
    )
    set_route_strategy("least_loaded")
    mark_route_start("busy")
    mark_route_start("busy")
    try:
        route = select_route(strategy="least_loaded")
        assert route is not None and route["id"] == "idle"
    finally:
        mark_route_end("busy")
        mark_route_end("busy")


def test_role_failover_models_in_kwargs_and_chain():
    save_routes(
        [
            {
                "id": "qwen",
                "provider": "qwen",
                "api_key": "sk-qwen-fb2",
                "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "model": "qwen-plus",
                "is_default": True,
            },
            {
                "id": "deepseek",
                "provider": "deepseek",
                "api_key": "sk-ds-fb2",
                "api_base": "https://api.deepseek.com",
                "model": "deepseek-v4-flash",
                "fallback": True,
            },
        ]
    )
    kwargs = llm_kwargs_for_role(
        {
            "preferred_provider": "qwen",
            "preferred_model": "qwen-max",
            "max_output_tokens": 1024,
            "context_window": 4000,
            "failover_models": ["deepseek-v4-flash"],
        }
    )
    assert kwargs["route_id"] == "qwen"
    assert kwargs["role_failover_models"] == ["deepseek-v4-flash"]
    chain = list_failover_chain(
        route_id="qwen",
        model="qwen-max",
        extra_models=["deepseek-v4-flash"],
    )
    ids = [r["id"] for r in chain]
    assert ids[0] == "qwen"
    assert "deepseek" in ids


def test_openrouter_provider_routing_normalizes_only():
    from backend.core.api_router import get_route

    upsert_route(
        {
            "id": "openrouter",
            "provider": "openrouter",
            "api_key": "sk-or-test",
            "api_base": "https://openrouter.ai/api/v1",
            "model": "openai/gpt-4o",
            "provider_routing": {"sort": "price", "allowed_providers": ["openai", "google"]},
            "is_default": True,
        }
    )
    route = get_route("openrouter")
    assert route is not None
    routing = route.get("provider_routing") or {}
    assert routing.get("sort") == "price"
    assert routing.get("only") == ["openai", "google"]


def test_token_plan_route_normalizes_provider_and_family_groups():
    route = normalize_route(
        {
            "id": "qwen",
            "name": "通義千問 Qwen",
            "provider": "qwen",
            "api_base": "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
            "catalog_url": "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/models",
            "model": "qwen3.8-flash",
            "allowed_models": ["qwen3.8-flash", "deepseek-v4-pro", "glm-5.2"],
            "catalog_models": [
                {"id": "qwen3.8-flash", "name": "qwen3.8-flash", "owned_by": "system"},
                {"id": "deepseek-v4-pro", "name": "deepseek-v4-pro", "owned_by": "system"},
                {"id": "glm-5.2", "name": "glm-5.2", "owned_by": "system"},
            ],
        }
    )
    assert route["provider"] == "token-plan"
    assert route["name"] == TOKEN_PLAN_LABEL
    owned = {row["id"]: row["owned_by"] for row in route["catalog_models"]}
    assert owned["deepseek-v4-pro"] == "deepseek"
    assert owned["glm-5.2"] == "zhipu"
    assert owned["qwen3.8-flash"] == "qwen"

    save_routes([{**route, "api_key": "sk-token-plan"}])
    state = public_router_state()
    groups = state["models_by_provider"]
    assert len(groups) == 3
    labels = {g["name"] for g in groups}
    assert any("DeepSeek" in label for label in labels)
    assert any("智譜 GLM" in label for label in labels)
    assert all(g["route_id"] == "qwen" for g in groups)


def test_role_preferred_still_pins_model_to_owner():
    save_routes(
        [
            {
                "id": "deepseek",
                "provider": "deepseek",
                "api_key": "sk-ds-pin",
                "api_base": "https://api.deepseek.com",
                "model": "deepseek-v4-flash",
                "is_default": True,
            },
            {
                "id": "qwen",
                "provider": "qwen",
                "api_key": "sk-qwen-pin",
                "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "model": "qwen-plus",
            },
        ],
        strategy="role_preferred",
    )
    set_route_strategy("role_preferred")
    route = select_route(model="qwen-max")
    assert route is not None and route["id"] == "qwen"
    pinned = resolve_target(model="qwen-max", route_id="qwen")
    assert pinned["route_id"] == "qwen"
    assert pinned["api_key"] == "sk-qwen-pin"
