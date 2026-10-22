"""A/B 評估框架（路線圖 Phase 12）。

對兩個變體做受控對比實驗，回答「哪個 Prompt／模型更好」：

    建立實驗（cases + variant_a/b）
        ▼
    逐 case 生成：call_llm（依變體注入 system / model）
        ▼
    4 維評估：MultiDimensionalEvaluator（準確/完整/清晰/相關）
        ▼
    勝負判定：總分差 ≤ tie_margin 為平手
        ▼
    聚合：勝/負/平、各維度均分、符號檢定 p 值（雙側精確二項）

設計要點：
- 生成一律經 backend.core.llm.call_llm（AGENTS.md 約束 #1），評估復用
  core.evaluation 引擎——測試以 monkeypatch 隔離，無需真實 API 金鑰。
- 持久化為單一 JSON 檔（EVOL_AB_STORE_PATH 可覆寫），與角色目錄同模式；
  模組級快取 + reset_cache() 供測試隔離。
- 案例數上限 EVOL_AB_MAX_CASES（預設 20）防止一次跑爆預算；
  平手邊界 EVOL_AB_TIE_MARGIN（預設 0.5 分）。
"""

from __future__ import annotations

import json
import logging
import math
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.core.evaluation import DIMENSION_NAMES, get_evaluator
from backend.core.llm import call_llm

logger = logging.getLogger(__name__)

DEFAULT_STORE = Path("backend/data/ab_experiments.json")
DEFAULT_TIE_MARGIN = 0.5
DEFAULT_MAX_CASES = 20
VALID_KINDS = ("prompt", "model")
SIGNIFICANCE_LEVEL = 0.05

_cache: dict[str, Any] | None = None


# ── 環境與持久化 ──


def _store_path() -> Path:
    raw = os.getenv("EVOL_AB_STORE_PATH", "").strip()
    return Path(raw) if raw else DEFAULT_STORE


def _tie_margin_default() -> float:
    try:
        return max(0.0, float(os.getenv("EVOL_AB_TIE_MARGIN", "").strip() or DEFAULT_TIE_MARGIN))
    except ValueError:
        return DEFAULT_TIE_MARGIN


def _max_cases() -> int:
    try:
        return max(1, int(os.getenv("EVOL_AB_MAX_CASES", "").strip() or DEFAULT_MAX_CASES))
    except ValueError:
        return DEFAULT_MAX_CASES


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load() -> dict[str, Any]:
    global _cache
    if _cache is not None:
        return _cache
    path = _store_path()
    data: dict[str, Any] = {"experiments": []}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and isinstance(loaded.get("experiments"), list):
                data = loaded
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("A/B 實驗檔損壞，重新開始：%s", exc)
    _cache = data
    return _cache


def _save(data: dict[str, Any]) -> None:
    path = _store_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.warning("A/B 實驗持久化失敗（僅保留記憶體）：%s", exc)


def reset_cache() -> None:
    """清空模組快取（測試與 EVOL_AB_STORE_PATH 切換後呼叫）。"""
    global _cache
    _cache = None


# ── 統計 ──


def sign_test_p_value(wins_a: int, wins_b: int) -> float:
    """符號檢定（雙側精確二項）：H0 為兩變體無差異。

    只計入分出勝負的案例；n 為 0 時回傳 1.0（無證據）。
    """
    n = int(wins_a) + int(wins_b)
    if n <= 0:
        return 1.0
    k = min(int(wins_a), int(wins_b))
    tail = sum(math.comb(n, i) for i in range(k + 1)) * (0.5 ** n)
    return min(1.0, 2.0 * tail)


# ── 實驗生命週期 ──


def _validate_variant(variant: Any, label: str, kind: str) -> dict[str, Any]:
    if not isinstance(variant, dict):
        # 統一以 ValueError 對應 HTTP 400（API 契約），不用 TypeError
        raise ValueError(f"{label} 必須為物件")  # noqa: TRY004
    name = str(variant.get("label") or "").strip()
    if not name:
        raise ValueError(f"{label} 需要 label")
    system = variant.get("system")
    model = variant.get("model")
    if kind == "prompt" and not str(system or "").strip():
        raise ValueError(f"{label}：kind=prompt 需要 system（Prompt 變體）")
    if kind == "model" and not str(model or "").strip():
        raise ValueError(f"{label}：kind=model 需要 model（模型變體）")
    return {
        "label": name,
        "system": str(system).strip() if system else None,
        "model": str(model).strip() if model else None,
    }


def create_experiment(
    name: str,
    cases: list[dict[str, Any]],
    variant_a: dict[str, Any],
    variant_b: dict[str, Any],
    kind: str = "prompt",
    tie_margin: float | None = None,
) -> dict[str, Any]:
    """建立 A/B 實驗（status=created，尚未執行）。

    Args:
        name: 實驗名稱
        cases: 測試案例 [{"query": str, "reference": str?}]，1..EVOL_AB_MAX_CASES 個
        variant_a / variant_b: {"label", "system"?, "model"?}；
            kind=prompt 需 system，kind=model 需 model
        kind: "prompt"（提示詞對比）或 "model"（模型對比）
        tie_margin: 平手邊界（總分差 ≤ margin 記平手），預設 EVOL_AB_TIE_MARGIN

    Raises:
        ValueError: 參數校驗失敗
    """
    kind = str(kind or "prompt").strip().lower()
    if kind not in VALID_KINDS:
        raise ValueError(f"kind 必須為 {'/'.join(VALID_KINDS)}")
    name = str(name or "").strip()
    if not name:
        raise ValueError("實驗需要 name")
    if not isinstance(cases, list) or not cases:
        raise ValueError("需要至少 1 個測試案例 cases=[{query}]")
    limit = _max_cases()
    if len(cases) > limit:
        raise ValueError(f"案例數超過上限 {limit}（收到 {len(cases)}）；可用 EVOL_AB_MAX_CASES 調整")
    clean_cases: list[dict[str, Any]] = []
    for i, case in enumerate(cases):
        if not isinstance(case, dict):
            # 統一以 ValueError 對應 HTTP 400（API 契約），不用 TypeError
            raise ValueError(f"cases[{i}] 必須為物件")  # noqa: TRY004
        query = str(case.get("query") or "").strip()
        if not query:
            raise ValueError(f"cases[{i}] 需要非空 query")
        entry: dict[str, Any] = {"query": query}
        reference = str(case.get("reference") or "").strip()
        if reference:
            entry["reference"] = reference
        clean_cases.append(entry)
    va = _validate_variant(variant_a, "variant_a", kind)
    vb = _validate_variant(variant_b, "variant_b", kind)
    margin = _tie_margin_default() if tie_margin is None else max(0.0, float(tie_margin))
    experiment = {
        "id": uuid.uuid4().hex[:12],
        "name": name,
        "kind": kind,
        "status": "created",
        "tie_margin": margin,
        "variant_a": va,
        "variant_b": vb,
        "cases": clean_cases,
        "results": [],
        "summary": None,
        "created_at": _now(),
        "completed_at": None,
    }
    data = _load()
    data["experiments"].append(experiment)
    _save(data)
    logger.info("建立 A/B 實驗 %s（%s，%d 案例）", experiment["id"], kind, len(clean_cases))
    return experiment


def _generate(variant: dict[str, Any], query: str, reference: str | None = None) -> str:
    """以變體設定生成回答；reference 對兩變體同樣注入，保持公平。"""
    prompt = query if not reference else f"{query}\n\n（參考答案：{reference}）"
    return call_llm(prompt, system=variant.get("system"), model=variant.get("model"))


def run_experiment(experiment_id: str) -> dict[str, Any]:
    """執行實驗：雙變體生成 → 4 維評估 → 勝負判定 → 聚合與顯著性。

    單一變體生成失敗記入該案例 errors，不中斷整個實驗；
    雙方都失敗或單方失敗的案例不計入勝負與均分。

    Raises:
        LookupError: 實驗不存在
    """
    data = _load()
    exp = _find(data, experiment_id)
    if exp is None:
        raise LookupError(f"實驗不存在：{experiment_id}")
    evaluator = get_evaluator()
    margin = float(exp.get("tie_margin") or 0.0)
    results: list[dict[str, Any]] = []
    wins_a = wins_b = ties = errors = 0
    dim_sums_a = {dim: 0.0 for dim in DIMENSION_NAMES}
    dim_sums_b = {dim: 0.0 for dim in DIMENSION_NAMES}
    overall_a_sum = overall_b_sum = 0.0
    scored = 0

    for case in exp.get("cases") or []:
        query = str(case.get("query") or "")
        reference = case.get("reference")
        row: dict[str, Any] = {"query": query, "winner": None, "errors": {}}
        answers: dict[str, str] = {}
        evals: dict[str, Any] = {}
        for key, variant in (("a", exp["variant_a"]), ("b", exp["variant_b"])):
            try:
                answer = _generate(variant, query, reference)
                answers[key] = str(answer or "")
                evals[key] = evaluator.evaluate(query, answers[key])
            except Exception as exc:  # noqa: BLE001 — 單變體失敗記入 errors，不中斷實驗
                row["errors"][key] = str(exc)[:300]
                logger.warning("A/B 實驗 %s 變體 %s 生成失敗：%s", experiment_id, key, exc)
        if "a" in evals and "b" in evals:
            score_a = float(evals["a"].overall)
            score_b = float(evals["b"].overall)
            row["score_a"] = round(score_a, 2)
            row["score_b"] = round(score_b, 2)
            row["dimensions_a"] = {dim: round(getattr(evals["a"], dim).score, 2) for dim in DIMENSION_NAMES}
            row["dimensions_b"] = {dim: round(getattr(evals["b"], dim).score, 2) for dim in DIMENSION_NAMES}
            row["answer_a"] = answers["a"][:500]
            row["answer_b"] = answers["b"][:500]
            diff = score_a - score_b
            if abs(diff) <= margin:
                row["winner"] = "tie"
                ties += 1
            elif diff > 0:
                row["winner"] = "a"
                wins_a += 1
            else:
                row["winner"] = "b"
                wins_b += 1
            scored += 1
            overall_a_sum += score_a
            overall_b_sum += score_b
            for dim in DIMENSION_NAMES:
                dim_sums_a[dim] += getattr(evals["a"], dim).score
                dim_sums_b[dim] += getattr(evals["b"], dim).score
        else:
            errors += 1
        results.append(row)

    p_value = sign_test_p_value(wins_a, wins_b)
    summary: dict[str, Any] = {
        "cases": len(exp.get("cases") or []),
        "scored": scored,
        "wins_a": wins_a,
        "wins_b": wins_b,
        "ties": ties,
        "errors": errors,
        "avg_overall_a": round(overall_a_sum / scored, 2) if scored else None,
        "avg_overall_b": round(overall_b_sum / scored, 2) if scored else None,
        "avg_dimensions_a": {dim: round(dim_sums_a[dim] / scored, 2) for dim in DIMENSION_NAMES} if scored else None,
        "avg_dimensions_b": {dim: round(dim_sums_b[dim] / scored, 2) for dim in DIMENSION_NAMES} if scored else None,
        "p_value": round(p_value, 6),
        "significant": bool(p_value < SIGNIFICANCE_LEVEL),
        "tie_margin": margin,
    }
    if wins_a > wins_b:
        summary["winner"] = exp["variant_a"]["label"]
    elif wins_b > wins_a:
        summary["winner"] = exp["variant_b"]["label"]
    else:
        summary["winner"] = None
    exp["results"] = results
    exp["summary"] = summary
    exp["status"] = "completed" if scored else "failed"
    exp["completed_at"] = _now()
    _save(data)
    logger.info("A/B 實驗 %s 完成：wins_a=%d wins_b=%d ties=%d errors=%d", experiment_id, wins_a, wins_b, ties, errors)
    return exp


def _find(data: dict[str, Any], experiment_id: str) -> dict[str, Any] | None:
    for exp in data.get("experiments") or []:
        if exp.get("id") == experiment_id:
            return exp
    return None


def get_experiment(experiment_id: str) -> dict[str, Any] | None:
    """實驗詳情（含逐案例結果）；不存在回傳 None。"""
    return _find(_load(), experiment_id)


def list_experiments() -> list[dict[str, Any]]:
    """實驗摘要列表（不含 cases 與逐案例結果詳情）。"""
    out: list[dict[str, Any]] = []
    for exp in _load().get("experiments") or []:
        out.append(
            {
                "id": exp.get("id"),
                "name": exp.get("name"),
                "kind": exp.get("kind"),
                "status": exp.get("status"),
                "cases": len(exp.get("cases") or []),
                "variant_a": (exp.get("variant_a") or {}).get("label"),
                "variant_b": (exp.get("variant_b") or {}).get("label"),
                "created_at": exp.get("created_at"),
                "completed_at": exp.get("completed_at"),
                "summary": exp.get("summary"),
            }
        )
    return out


def delete_experiment(experiment_id: str) -> bool:
    """刪除實驗；不存在回傳 False。"""
    data = _load()
    before = len(data.get("experiments") or [])
    data["experiments"] = [e for e in data.get("experiments") or [] if e.get("id") != experiment_id]
    if len(data["experiments"]) == before:
        return False
    _save(data)
    return True
