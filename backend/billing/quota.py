"""配額：預扣、結算、餘額檢查。"""

from __future__ import annotations

from typing import Any

from backend.billing.errors import InsufficientCreditsError
from backend.billing.store import BillingStore, get_billing_store


class BillingService:
    def __init__(self, store: BillingStore | None = None) -> None:
        self.store = store or get_billing_store()

    def ensure_account(self, user_id: str, plan_id: str = "free") -> dict[str, Any]:
        return self.store.ensure_account(user_id, plan_id)

    def get_account(self, user_id: str) -> dict[str, Any]:
        row = self.store.get_account(user_id)
        if row:
            return row
        return self.ensure_account(user_id)

    def set_plan(self, user_id: str, plan_id: str) -> dict[str, Any]:
        return self.store.set_plan(user_id, plan_id)

    def topup_credits(self, user_id: str, credits: float, *, reference: str = "topup", meta: dict | None = None) -> dict:
        entry = self.store.credit(user_id, credits, source="topup", reference=reference, meta=meta)
        return {"account": self.get_account(user_id), "entry": entry}

    def debit_credits(self, user_id: str, credits: float, *, source: str, reference: str = "", meta: dict | None = None) -> dict:
        return self.store.debit(user_id, credits, source=source, reference=reference, meta=meta)

    def ensure_can_afford(self, user_id: str, credits: float) -> None:
        acct = self.get_account(user_id)
        if float(acct["balance_credits"]) < float(credits):
            raise InsufficientCreditsError(
                balance_credits=float(acct["balance_credits"]),
                required_credits=float(credits),
            )

    def reserve(self, user_id: str, estimated_credits: float) -> str:
        self.ensure_can_afford(user_id, estimated_credits)
        return self.store.create_reservation(user_id, estimated_credits)

    def settle(self, reservation_id: str, user_id: str, actual_credits: float, *, source: str, reference: str = "", meta: dict | None = None) -> dict:
        self.debit_credits(user_id, actual_credits, source=source, reference=reference, meta=meta)
        self.store.settle_reservation(reservation_id, actual_credits)
        return self.get_account(user_id)

    def usage_events(self, user_id: str, limit: int = 50) -> list[dict]:
        return self.store.list_usage_events(user_id, limit)

    def ledger(self, user_id: str, limit: int = 50) -> list[dict]:
        return self.store.list_ledger(user_id, limit)


_SERVICE: BillingService | None = None


def get_billing_service() -> BillingService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = BillingService()
    return _SERVICE


def reset_billing_service(service: BillingService | None = None) -> None:
    global _SERVICE
    _SERVICE = service
