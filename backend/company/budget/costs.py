"""CostTracker：估算 LLM 呼叫成本（token 計價）（自 backend.company.budget 抽出）。"""

from __future__ import annotations

from backend.company.rate_card import estimate_usage_cost


class CostTracker:
    """估算 LLM 呼叫成本（含快取／推理／多模態收費項）。"""

    @staticmethod
    def estimate_cost(
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        *,
        cached_input_tokens: int = 0,
        cache_write_tokens: int = 0,
        reasoning_tokens: int = 0,
        image_tokens: int = 0,
        audio_tokens: int = 0,
        embedding_tokens: int = 0,
        **extra: int,
    ) -> float:
        """根據各收費項用量估算成本（USD）。"""
        return estimate_usage_cost(
            model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached_input_tokens,
            cache_write_tokens=cache_write_tokens,
            reasoning_tokens=reasoning_tokens,
            image_tokens=image_tokens,
            audio_tokens=audio_tokens,
            embedding_tokens=embedding_tokens,
            **extra,
        )

    @staticmethod
    def estimate_cost_rough(model: str, complexity: str = "medium") -> float:
        """粗略估算（無 token 計數時使用）。"""
        base_tokens = {"low": 500, "medium": 2000, "high": 8000}
        tokens = base_tokens.get(complexity, 2000)
        return CostTracker.estimate_cost(model, input_tokens=tokens, output_tokens=tokens)
