"""貢獻者獎勵入帳 — LLM settle 時寫入 contribution_unlocked + fault_pool 平台抽成。"""
from __future__ import annotations

import os
from typing import Any

from backend.billing.fault_pool import credit_fault_pool, DEFAULT_PLATFORM_TAKE
from backend.billing.pool_store import get_pool_store
from backend.billing.pool_types import POOL_CONTRIBUTION_UNLOCKED
from backend.billing.reward_engine import compute_reward

_PLATFORM_KEY_IDS = frozenset(
    {
        "platform_default",
        "public_pool_premium",
        "",
    }
)


def _default_key_id() -> str:
    return os.environ.get("LINKIN_DEFAULT_API_KEY_ID", "platform_default")


def is_contributor_key(key_id: str | None) -> bool:
    if not key_id:
        return False
    kid = key_id.strip()
    if kid in _PLATFORM_KEY_IDS or kid == _default_key_id():
        return False
    return get_pool_store().resolve_contributor_account(kid) is not None


def settle_contributor_reward(
    *,
    task_id: str,
    consumer_account_id: str,
    key_id: str | None,
    actual_api_cost: float,
    lock_multiplier: float = 1.0,
    input_tokens: int = 0,
    output_tokens: int = 0,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    共享池 Key 服務一次 LLM 調用後：
    - contributor_reward → POOL_CONTRIBUTION_UNLOCKED（不可轉贈）
    - platform_take → fault_pool
    """
    if actual_api_cost <= 0 or not is_contributor_key(key_id):
        return {"credited": False, "reason": "no_contributor_key", "key_id": key_id}

    store = get_pool_store()
    contributor_account = store.resolve_contributor_account(str(key_id))
    if not contributor_account:
        return {"credited": False, "reason": "unknown_key", "key_id": key_id}

    take_rate = float(store.get_routing_runtime("platform_take_rate", DEFAULT_PLATFORM_TAKE))
    take_param = take_rate if 0.2 <= take_rate <= 0.4 else 0.3
    reward = compute_reward(
        actual_api_cost,
        lock_multiplier=lock_multiplier,
        platform_take=take_param,
    )
    contributor_amount = float(reward["contributor_reward"])
    platform_take = float(reward["platform_take"])
    if contributor_amount <= 0:
        return {"credited": False, "reason": "zero_reward", **reward}

    store.credit_pool(
        contributor_account,
        POOL_CONTRIBUTION_UNLOCKED,
        contributor_amount,
        source="contributor_reward",
        description=f"共享池 Key 服務獎勵 · {key_id}",
        task_id=task_id,
        origin="contributor_reward",
    )
    if platform_take > 0:
        credit_fault_pool(
            platform_take,
            "platform_take_llm_settle",
            account_id=contributor_account,
            task_id=task_id,
            source="platform_take",
            meta={
                "consumer_account_id": consumer_account_id,
                "key_id": key_id,
                "gross_reward": reward.get("gross_reward"),
                **(meta or {}),
            },
        )

    store.increment_key_usage(
        str(key_id),
        tokens=input_tokens + output_tokens,
        credits=actual_api_cost,
    )

    return {
        "credited": True,
        "contributor_account_id": contributor_account,
        "consumer_account_id": consumer_account_id,
        "key_id": key_id,
        "pool_type": POOL_CONTRIBUTION_UNLOCKED,
        **reward,
    }
