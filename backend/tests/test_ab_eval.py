"""A/B 評估框架：建立驗證、執行聚合、顯著性、持久化、HTTP API。

生成與評估以 monkeypatch 隔離（AGENTS.md 約束 #2），無需真實 API 金鑰。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.core.evaluation import DimensionResult, EvaluationResult
from backend.services import ab_eval


@pytest.fixture()
def ab_env(tmp_path, monkeypatch):
    monkeypatch.setenv("EVOL_AB_STORE_PATH", str(tmp_path / "ab.json"))
    ab_eval.reset_cache()
    yield tmp_path
    ab_eval.reset_cache()


def _stub_evaluation(score: float) -> EvaluationResult:
    result = EvaluationResult(source="test")
    for dim in ("accuracy", "completeness", "clarity", "relevance"):
        setattr(result, dim, DimensionResult(score, "stub"))
    result.overall = score
    return result


class _StubEvaluator:
    """依答案內容回傳固定分數：含『優質』→ 9 分，否則 3 分。"""

    def evaluate(self, query: str, answer: str) -> EvaluationResult:
        return _stub_evaluation(9.0 if "優質" in answer else 3.0)


@pytest.fixture()
def stubbed(monkeypatch):
    """固定生成與評估：GOOD 變體產出優質答案，其餘產出劣質答案。"""

    def _call_llm(prompt, system=None, model=None, **kwargs):
        if (system or "").startswith("GOOD") or model == "good-model":
            return "這是一個優質的回答。"
        return "随便写点东西。"

    monkeypatch.setattr(ab_eval, "call_llm", _call_llm)
    monkeypatch.setattr(ab_eval, "get_evaluator", lambda: _StubEvaluator())


# ── 建立與驗證 ──


def test_create_validation(ab_env):
    va = {"label": "a", "system": "s"}
    vb = {"label": "b", "system": "s"}
    with pytest.raises(ValueError):
        ab_eval.create_experiment("", [{"query": "q"}], va, vb)
    with pytest.raises(ValueError):
        ab_eval.create_experiment("x", [], va, vb)
    with pytest.raises(ValueError):
        ab_eval.create_experiment("x", [{"query": ""}], va, vb)
    # kind=prompt 缺 system
    with pytest.raises(ValueError):
        ab_eval.create_experiment("x", [{"query": "q"}], {"label": "a"}, vb)
    # kind=model 缺 model
    with pytest.raises(ValueError):
        ab_eval.create_experiment(
            "x", [{"query": "q"}], {"label": "a", "model": "m1"}, {"label": "b"}, kind="model"
        )
    # 非法 kind
    with pytest.raises(ValueError):
        ab_eval.create_experiment("x", [{"query": "q"}], va, vb, kind="bogus")


def test_max_cases_guard(ab_env, monkeypatch):
    monkeypatch.setenv("EVOL_AB_MAX_CASES", "2")
    cases = [{"query": f"q{i}"} for i in range(3)]
    with pytest.raises(ValueError, match="上限"):
        ab_eval.create_experiment(
            "x", cases, {"label": "a", "system": "s"}, {"label": "b", "system": "s"}
        )


# ── 執行與聚合 ──


def test_run_prompt_experiment_a_wins(ab_env, stubbed):
    exp = ab_eval.create_experiment(
        "提示詞對比",
        [{"query": "問題一"}, {"query": "問題二"}, {"query": "問題三"}],
        {"label": "精簡版", "system": "GOOD 精簡提示"},
        {"label": "囉嗦版", "system": "BAD 囉嗦提示"},
    )
    assert exp["status"] == "created"
    done = ab_eval.run_experiment(exp["id"])
    summary = done["summary"]
    assert done["status"] == "completed"
    assert summary["wins_a"] == 3
    assert summary["wins_b"] == 0
    assert summary["ties"] == 0
    assert summary["errors"] == 0
    assert summary["winner"] == "精簡版"
    assert summary["avg_overall_a"] == 9.0
    assert summary["avg_overall_b"] == 3.0
    assert summary["avg_dimensions_a"]["accuracy"] == 9.0
    # n=3 全勝：雙側精確二項 p = 2 * (1/2)^3 = 0.25，樣本太少不顯著
    assert summary["p_value"] == 0.25
    assert summary["significant"] is False
    assert len(done["results"]) == 3
    assert done["results"][0]["winner"] == "a"
    assert done["results"][0]["dimensions_a"]["clarity"] == 9.0


def test_run_model_experiment(ab_env, stubbed):
    exp = ab_eval.create_experiment(
        "模型對比",
        [{"query": "q1"}],
        {"label": "A", "model": "good-model"},
        {"label": "B", "model": "bad-model"},
        kind="model",
    )
    done = ab_eval.run_experiment(exp["id"])
    assert done["summary"]["wins_a"] == 1
    assert done["summary"]["winner"] == "A"


def test_significance_with_enough_samples(ab_env, monkeypatch):
    monkeypatch.setenv("EVOL_AB_MAX_CASES", "12")

    def _call_llm(prompt, system=None, model=None, **kwargs):
        return "優質" if (system or "").startswith("GOOD") else "普通"

    monkeypatch.setattr(ab_eval, "call_llm", _call_llm)
    monkeypatch.setattr(ab_eval, "get_evaluator", lambda: _StubEvaluator())
    exp = ab_eval.create_experiment(
        "顯著性",
        [{"query": f"q{i}"} for i in range(12)],
        {"label": "a", "system": "GOOD"},
        {"label": "b", "system": "BAD"},
    )
    done = ab_eval.run_experiment(exp["id"])
    # n=12 全勝：p = 2 * (1/2)^12 ≈ 0.000488 < 0.05（summary 中取整到 6 位）
    assert done["summary"]["wins_a"] == 12
    assert done["summary"]["p_value"] == round(2 / 4096, 6)
    assert done["summary"]["significant"] is True


def test_tie_margin(ab_env, monkeypatch):
    class _CloseEvaluator:
        """兩變體分數差 0.2 < 預設 0.5 → 平手。"""

        def evaluate(self, query: str, answer: str) -> EvaluationResult:
            return _stub_evaluation(9.0 if "優質" in answer else 8.8)

    monkeypatch.setattr(
        ab_eval,
        "call_llm",
        lambda prompt, system=None, model=None, **kw: "優質" if (system or "").startswith("GOOD") else "普通",
    )
    monkeypatch.setattr(ab_eval, "get_evaluator", lambda: _CloseEvaluator())
    exp = ab_eval.create_experiment(
        "平手",
        [{"query": "q"}],
        {"label": "a", "system": "GOOD"},
        {"label": "b", "system": "BAD"},
    )
    done = ab_eval.run_experiment(exp["id"])
    assert done["summary"]["ties"] == 1
    assert done["summary"]["winner"] is None
    assert done["results"][0]["winner"] == "tie"


def test_generation_error_counted(ab_env, monkeypatch):
    def _flaky(prompt, system=None, model=None, **kw):
        if (system or "").startswith("BAD"):
            raise RuntimeError("boom")
        return "優質回答"

    monkeypatch.setattr(ab_eval, "call_llm", _flaky)
    monkeypatch.setattr(ab_eval, "get_evaluator", lambda: _StubEvaluator())
    exp = ab_eval.create_experiment(
        "錯誤",
        [{"query": "q"}],
        {"label": "a", "system": "GOOD"},
        {"label": "b", "system": "BAD"},
    )
    done = ab_eval.run_experiment(exp["id"])
    assert done["summary"]["errors"] == 1
    assert done["summary"]["scored"] == 0
    assert done["status"] == "failed"
    assert done["results"][0]["errors"]["b"] == "boom"


def test_reference_injected_for_both_variants(ab_env, monkeypatch):
    seen: list[str] = []

    def _capture(prompt, system=None, model=None, **kw):
        seen.append(prompt)
        return "優質"

    monkeypatch.setattr(ab_eval, "call_llm", _capture)
    monkeypatch.setattr(ab_eval, "get_evaluator", lambda: _StubEvaluator())
    exp = ab_eval.create_experiment(
        "參考",
        [{"query": "q", "reference": "標準答案"}],
        {"label": "a", "system": "A"},
        {"label": "b", "system": "B"},
        tie_margin=99,
    )
    ab_eval.run_experiment(exp["id"])
    assert len(seen) == 2
    assert all("標準答案" in p for p in seen)


# ── 統計 ──


def test_sign_test_p_value():
    assert ab_eval.sign_test_p_value(0, 0) == 1.0
    assert ab_eval.sign_test_p_value(5, 5) == 1.0
    assert ab_eval.sign_test_p_value(3, 0) == pytest.approx(0.25)
    assert ab_eval.sign_test_p_value(10, 0) == pytest.approx(2 / 1024)
    assert ab_eval.sign_test_p_value(8, 2) == pytest.approx(2 * (1 + 10 + 45) / 1024)


# ── 持久化與 CRUD ──


def test_persistence_roundtrip(ab_env, stubbed):
    exp = ab_eval.create_experiment(
        "持久化",
        [{"query": "q"}],
        {"label": "a", "system": "GOOD"},
        {"label": "b", "system": "BAD"},
    )
    ab_eval.run_experiment(exp["id"])
    ab_eval.reset_cache()  # 模擬進程重啟：應從 JSON 檔恢復
    loaded = ab_eval.get_experiment(exp["id"])
    assert loaded is not None
    assert loaded["status"] == "completed"
    assert loaded["summary"]["wins_a"] == 1
    assert [e["id"] for e in ab_eval.list_experiments()] == [exp["id"]]
    assert ab_eval.delete_experiment(exp["id"]) is True
    assert ab_eval.get_experiment(exp["id"]) is None
    assert ab_eval.delete_experiment(exp["id"]) is False


def test_corrupt_store_recovers(ab_env):
    (ab_env / "ab.json").write_text("{ not json", encoding="utf-8")
    ab_eval.reset_cache()
    assert ab_eval.list_experiments() == []


def test_run_missing_experiment(ab_env):
    with pytest.raises(LookupError):
        ab_eval.run_experiment("nonexistent0")


# ── HTTP API（backend.main 掛載）──


def test_http_api(ab_env, stubbed):
    from backend.main import app

    with TestClient(app) as client:
        created = client.post(
            "/ab/experiments",
            json={
                "name": "HTTP 實驗",
                "kind": "prompt",
                "variant_a": {"label": "A", "system": "GOOD prompt"},
                "variant_b": {"label": "B", "system": "BAD prompt"},
                "cases": [{"query": "問題一"}, {"query": "問題二"}],
            },
        )
        assert created.status_code == 200
        exp_id = created.json()["id"]

        bad = client.post(
            "/ab/experiments",
            json={
                "name": "x",
                "variant_a": {"label": "a"},  # kind=prompt 缺 system → 400
                "variant_b": {"label": "b", "system": "s"},
                "cases": [{"query": "q"}],
            },
        )
        assert bad.status_code == 400

        ran = client.post(f"/ab/experiments/{exp_id}/run")
        assert ran.status_code == 200
        assert ran.json()["summary"]["wins_a"] == 2

        listing = client.get("/ab/experiments")
        assert listing.status_code == 200
        assert any(e["id"] == exp_id for e in listing.json()["experiments"])

        detail = client.get(f"/ab/experiments/{exp_id}")
        assert detail.status_code == 200
        assert detail.json()["status"] == "completed"

        assert client.get("/ab/experiments/nonexistent0").status_code == 404
        assert client.post("/ab/experiments/nonexistent0/run").status_code == 404

        deleted = client.delete(f"/ab/experiments/{exp_id}")
        assert deleted.status_code == 200
        assert client.get(f"/ab/experiments/{exp_id}").status_code == 404
        assert client.delete(f"/ab/experiments/{exp_id}").status_code == 404
