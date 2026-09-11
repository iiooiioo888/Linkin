"""靈境積分計費錯誤。"""

from __future__ import annotations


class BillingError(Exception):
    def __init__(self, message: str, code: str = "BILLING_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class InsufficientCreditsError(BillingError):
    def __init__(
        self,
        message: str = "靈境積分不足，無法執行此操作。請升級方案或充值後再試。",
        *,
        balance_credits: float = 0.0,
        required_credits: float = 0.0,
    ) -> None:
        super().__init__(message, code="INSUFFICIENT_CREDITS")
        self.balance_credits = balance_credits
        self.required_credits = required_credits


class FeatureNotEntitledError(BillingError):
    def __init__(self, feature: str, plan_id: str) -> None:
        super().__init__(
            f"目前方案（{plan_id}）未包含「{feature}」功能包，請升級方案。",
            code="FEATURE_NOT_ENTITLED",
        )
        self.feature = feature
        self.plan_id = plan_id
