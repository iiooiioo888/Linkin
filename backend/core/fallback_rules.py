"""規則回退評分。

LLM 評估失敗時使用。每個規則只看字串，不呼叫模型。
回傳的 EvaluationResult.source 為 rule_fallback；呼叫方必須帶上 fallback_reason。
"""

from __future__ import annotations

import re


def _types():
    from backend.core.evaluation import DIMENSION_WEIGHTS, DimensionResult, EvaluationResult

    return DIMENSION_WEIGHTS, DimensionResult, EvaluationResult


class RuleBasedFallback:
    """規則啟發式評估（LLM 失敗時的降級方案）。"""

    @staticmethod
    def evaluate(query: str, answer: str):
        """基於規則評估回答品質。"""
        weights, _dimension, evaluation_result = _types()
        result = evaluation_result(source="rule_fallback")
        result.accuracy = RuleBasedFallback._score_accuracy(query, answer)
        result.completeness = RuleBasedFallback._score_completeness(query, answer)
        result.clarity = RuleBasedFallback._score_clarity(answer)
        result.relevance = RuleBasedFallback._score_relevance(query, answer)
        result.overall = sum(
            getattr(result, dim).score * weight for dim, weight in weights.items()
        )
        return result

    @staticmethod
    def _score_accuracy(query: str, answer: str):
        """準確性：回答不應過短或過長，不應包含不確定性標記。"""
        _weights, dimension, _evaluation = _types()
        del query
        score = 6.0
        reasons: list[str] = []

        if len(answer) < 20:
            score -= 3.0
            reasons.append("回答過短")
        elif len(answer) > 5000:
            score -= 1.0
            reasons.append("回答過長，可能包含冗餘")

        uncertainty_patterns = [
            r"我不[確确]定", r"可能不準", r"僅供參考", r"我不確定",
            r"I'm not sure", r"might be wrong", r"不确定",
        ]
        for pattern in uncertainty_patterns:
            if re.search(pattern, answer, re.IGNORECASE):
                score -= 1.5
                reasons.append("包含不確定性標記")
                break

        sentences = [s.strip() for s in re.split(r"[。！？\n]", answer) if s.strip()]
        if len(sentences) > 3:
            unique_ratio = len(set(sentences)) / len(sentences)
            if unique_ratio < 0.6:
                score -= 2.0
                reasons.append("大量重複內容")

        return dimension(
            score=max(0.0, min(10.0, score)),
            reason="；".join(reasons) if reasons else "基本規則通過",
        )

    @staticmethod
    def _score_completeness(query: str, answer: str):
        """完整性：查詢關鍵詞在回答中的覆蓋率。"""
        _weights, dimension, _evaluation = _types()
        stop_words = {
            "的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都",
            "一", "一個", "上", "也", "很", "到", "說", "要", "去", "你",
            "會", "著", "沒有", "看", "好", "自己", "這", "他", "她", "它",
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "can", "to", "of",
            "in", "for", "on", "with", "at", "by", "from", "as", "into",
            "about", "請", "问", "問", "什么", "什麼", "怎么", "怎麼",
            "如何", "哪些", "哪个", "哪個", "嗎", "吗", "呢", "吧",
        }
        query_words = set(re.findall(r"[\w\u4e00-\u9fff]+", query.lower()))
        query_words -= stop_words

        if not query_words:
            return dimension(score=6.0, reason="無法提取查詢關鍵詞")

        answer_lower = answer.lower()
        covered = sum(1 for word in query_words if word in answer_lower)
        coverage = covered / len(query_words)
        score = 3.0 + coverage * 7.0
        return dimension(
            score=max(0.0, min(10.0, score)),
            reason=f"關鍵詞覆蓋率 {coverage:.0%}（{covered}/{len(query_words)}）",
        )

    @staticmethod
    def _score_clarity(answer: str):
        """清晰度：結構化指標。"""
        _weights, dimension, _evaluation = _types()
        score = 6.0
        reasons: list[str] = []

        paragraphs = [part.strip() for part in answer.split("\n\n") if part.strip()]
        if len(paragraphs) >= 2:
            score += 1.0
            reasons.append("有段落分隔")
        elif len(answer) > 500 and len(paragraphs) < 2:
            score -= 1.0
            reasons.append("長回答缺乏段落結構")

        list_patterns = [r"^\d+[\.\)、]", r"^[-•*]\s", r"^第[一二三四五六七八九十]"]
        has_list = any(
            re.search(pattern, line, re.MULTILINE)
            for pattern in list_patterns
            for line in answer.split("\n")
        )
        if has_list:
            score += 1.0
            reasons.append("使用列表結構")

        has_heading = bool(re.search(r"^#{1,3}\s|^[一二三四五六七八九十]+[、.]", answer, re.MULTILINE))
        if has_heading:
            score += 0.5
            reasons.append("有標題層級")

        long_sentences = [sentence for sentence in re.split(r"[。！？\n]", answer) if len(sentence) > 200]
        if long_sentences:
            score -= 1.0
            reasons.append(f"{len(long_sentences)} 個過長句子")

        return dimension(
            score=max(0.0, min(10.0, score)),
            reason="；".join(reasons) if reasons else "基本結構通過",
        )

    @staticmethod
    def _score_relevance(query: str, answer: str):
        """相關性：查詢意圖與回答的匹配度。"""
        _weights, dimension, _evaluation = _types()
        score = 6.0
        reasons: list[str] = []
        query_lower = query.lower()
        answer_lower = answer.lower()

        if any(word in query_lower for word in ["怎么", "怎麼", "如何", "how"]):
            if any(word in answer_lower for word in ["步骤", "步驟", "方法", "首先", "第一", "step"]):
                score += 1.5
                reasons.append("問題類型匹配（how-to）")

        if any(word in query_lower for word in ["什么是", "什麼是", "是什么", "what is"]):
            if any(word in answer_lower for word in ["是", "指", "定义", "定義", "means", "refers"]):
                score += 1.0
                reasons.append("問題類型匹配（定義）")

        query_chars = set(re.findall(r"[\u4e00-\u9fff]", query))
        if query_chars and len(answer) > 200:
            answer_chars = set(re.findall(r"[\u4e00-\u9fff]", answer))
            overlap = len(query_chars & answer_chars) / len(query_chars)
            if overlap < 0.3:
                score -= 2.0
                reasons.append("回答與查詢關聯度低")

        return dimension(
            score=max(0.0, min(10.0, score)),
            reason="；".join(reasons) if reasons else "基本相關性通過",
        )
