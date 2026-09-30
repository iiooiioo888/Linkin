"""多維度評估引擎（優化 #1）。

提供：
1. MultiDimensionalEvaluator: 4 維度獨立評分（準確性/完整性/清晰度/相關性）
2. RuleBasedFallback: LLM 評估失敗時的規則啟發式評分（實作在 fallback_rules.py）
3. CrossModelEvaluator: 不同模型交叉評估，打破自評偏差

評分流程：
  LLM 多維度評估 → 解析成功 → 加權總分
                 → 解析失敗 → 規則 fallback
  可選：交叉評估（第二模型覆核）
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from backend.core.fallback_rules import RuleBasedFallback
from backend.core.llm import call_llm, parse_json_response
from backend.core.stage_router import resolve_stage_model

logger = logging.getLogger(__name__)

# ── 維度權重（總和 = 1.0）──
DIMENSION_WEIGHTS = {
    "accuracy": 0.35,
    "completeness": 0.30,
    "clarity": 0.20,
    "relevance": 0.15,
}

DIMENSION_NAMES = list(DIMENSION_WEIGHTS.keys())

# ── Prompt 模板 ──
MULTI_DIM_EVALUATE_PROMPT = """你是一位嚴格的回答品質審查員。請從以下 4 個維度獨立評估回答品質。

【使用者問題】
{query}

【待評估回答】
{answer}

請對每個維度給出 0-10 分（一位小數）和簡短評語：
1. 準確性（accuracy）：資訊是否正確、有無事實錯誤
2. 完整性（completeness）：是否涵蓋問題的所有關鍵要點
3. 清晰度（clarity）：表達是否清楚、結構是否合理
4. 相關性（relevance）：是否切題、有無偏題或冗餘

只輸出 JSON，格式如下：
{{
  "accuracy": {{"score": <0-10>, "reason": "<評語>"}},
  "completeness": {{"score": <0-10>, "reason": "<評語>"}},
  "clarity": {{"score": <0-10>, "reason": "<評語>"}},
  "relevance": {{"score": <0-10>, "reason": "<評語>"}}
}}"""

CROSS_MODEL_PROMPT = """你是另一位審查員，請覆核以下評估結果是否合理。

【使用者問題】
{query}

【回答】
{answer}

【原評估】
{original_evaluation}

你是否同意原評估？若不同意，請給出你認為更準確的評分。
只輸出 JSON：
{{
  "agree": true/false,
  "override_scores": {{"accuracy": <0-10>, "completeness": <0-10>, "clarity": <0-10>, "relevance": <0-10>}},
  "reason": "<覆核理由>"
}}"""


@dataclass
class DimensionResult:
    """單維度評估結果。"""
    score: float
    reason: str


@dataclass
class EvaluationResult:
    """多維度評估完整結果。"""
    accuracy: DimensionResult = field(default_factory=lambda: DimensionResult(0.0, ""))
    completeness: DimensionResult = field(default_factory=lambda: DimensionResult(0.0, ""))
    clarity: DimensionResult = field(default_factory=lambda: DimensionResult(0.0, ""))
    relevance: DimensionResult = field(default_factory=lambda: DimensionResult(0.0, ""))
    overall: float = 0.0
    source: str = "llm"  # "llm" | "rule_fallback" | "cross_model"
    fallback_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        fallback_used = self.source == "rule_fallback"
        return {
            "accuracy": {"score": self.accuracy.score, "reason": self.accuracy.reason},
            "completeness": {"score": self.completeness.score, "reason": self.completeness.reason},
            "clarity": {"score": self.clarity.score, "reason": self.clarity.reason},
            "relevance": {"score": self.relevance.score, "reason": self.relevance.reason},
            "overall": round(self.overall, 2),
            "source": self.source,
            "score_source": "fallback" if fallback_used else "llm",
            "fallback_used": fallback_used,
            "fallback_reason": self.fallback_reason if fallback_used else "",
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> EvaluationResult:
        result = EvaluationResult()
        for dim in DIMENSION_NAMES:
            dim_data = data.get(dim, {})
            if isinstance(dim_data, dict):
                setattr(result, dim, DimensionResult(
                    score=float(dim_data.get("score", 0)),
                    reason=str(dim_data.get("reason", "")),
                ))
        result.overall = float(data.get("overall", 0))
        result.source = str(data.get("source", "llm"))
        result.fallback_reason = str(data.get("fallback_reason", ""))
        return result


class MultiDimensionalEvaluator:
    """多維度評估器。"""

    def evaluate(self, query: str, answer: str) -> EvaluationResult:
        """執行 LLM 多維度評估，失敗時降級為規則評估。"""
        try:
            prompt = MULTI_DIM_EVALUATE_PROMPT.format(query=query, answer=answer)
            model = resolve_stage_model("evaluate", query=query)
            raw = call_llm(prompt, model=model)
            data = parse_json_response(raw)
            return self._parse_evaluation(data, source="llm")
        except Exception as exc:
            logger.warning("LLM 多維度評估失敗，降級為規則評估：%s", exc)
            result = RuleBasedFallback.evaluate(query, answer)
            result.fallback_reason = f"LLM 評估失敗：{exc}"
            return result

    def _parse_evaluation(self, data: dict, source: str = "llm") -> EvaluationResult:
        """解析 LLM 評估 JSON，容錯處理。"""
        result = EvaluationResult(source=source)
        for dim in DIMENSION_NAMES:
            dim_data = data.get(dim, {})
            if isinstance(dim_data, dict):
                score = max(0.0, min(10.0, float(dim_data.get("score", 0))))
                reason = str(dim_data.get("reason", ""))
            elif isinstance(dim_data, (int, float)):
                score = max(0.0, min(10.0, float(dim_data)))
                reason = ""
            else:
                score = 0.0
                reason = "解析失敗"
            setattr(result, dim, DimensionResult(score=score, reason=reason))

        # 加權總分
        result.overall = sum(
            getattr(result, dim).score * weight
            for dim, weight in DIMENSION_WEIGHTS.items()
        )
        # 向後相容：舊版 {"score": 9, "strengths": "..."} 沒有四維欄位
        if result.overall == 0:
            legacy = data.get("overall", data.get("score"))
            try:
                score = max(0.0, min(10.0, float(legacy))) if legacy is not None else 0.0
            except (TypeError, ValueError):
                score = 0.0
            if score > 0:
                reason = str(data.get("strengths") or data.get("weaknesses") or "legacy")
                for dim in DIMENSION_NAMES:
                    setattr(result, dim, DimensionResult(score=score, reason=reason))
                result.overall = score
        return result


class CrossModelEvaluator:
    """交叉評估器：用不同模型覆核評估結果，打破自評偏差。"""

    @staticmethod
    def cross_evaluate(
        query: str,
        answer: str,
        original_evaluation: dict[str, Any],
        cross_model: str | None = None,
    ) -> EvaluationResult | None:
        """用第二個模型覆核評估結果。

        Args:
            query: 使用者問題
            answer: 待評估回答
            original_evaluation: 原始多維度評估結果
            cross_model: 覆核模型（None 時使用環境變數配置）

        Returns:
            覆核後的評估結果，失敗時回傳 None（保留原始評估）
        """
        if not cross_model:
            import os
            cross_model = os.getenv("EVOL_CROSS_EVAL_MODEL")
            if not cross_model:
                if os.getenv("EVOL_CROSS_EVAL_AUTO", "").lower() == "true":
                    cross_model = resolve_stage_model("cross_eval", query=query)
                else:
                    return None  # 未配置覆核模型，跳過

        try:
            prompt = CROSS_MODEL_PROMPT.format(
                query=query,
                answer=answer,
                original_evaluation=json.dumps(original_evaluation, ensure_ascii=False, indent=2),
            )
            raw = call_llm(prompt, model=cross_model)
            data = parse_json_response(raw)

            if not data.get("agree", True):
                # 覆核模型不同意，使用覆核分數
                override = data.get("override_scores", {})
                result = EvaluationResult(source="cross_model")
                for dim in DIMENSION_NAMES:
                    score = max(0.0, min(10.0, float(override.get(dim, 0))))
                    setattr(result, dim, DimensionResult(score=score, reason="交叉評估覆核"))
                result.overall = sum(
                    getattr(result, dim).score * weight
                    for dim, weight in DIMENSION_WEIGHTS.items()
                )
                logger.info(
                    "交叉評估覆核：原分 %.1f → 新分 %.1f（理由：%s）",
                    original_evaluation.get("overall", 0),
                    result.overall,
                    data.get("reason", ""),
                )
                return result

            return None  # 覆核模型同意，保留原始評估

        except Exception as exc:
            logger.warning("交叉評估失敗（保留原始評估）：%s", exc)
            return None


# ── 模組級單例 ──
_evaluator: MultiDimensionalEvaluator | None = None


def get_evaluator() -> MultiDimensionalEvaluator:
    """取得全域評估器單例。"""
    global _evaluator
    if _evaluator is None:
        _evaluator = MultiDimensionalEvaluator()
    return _evaluator
