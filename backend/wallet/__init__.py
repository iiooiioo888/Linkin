"""向後相容：wallet 模組委派至 billing。"""

from backend.billing import (
    FeatureNotEntitledError,
    InsufficientCreditsError,
    get_billing_service,
    register_billing,
)
from backend.billing.errors import InsufficientCreditsError as InsufficientBalanceError
from backend.billing.quota import get_billing_service as get_wallet_service

register_wallet = register_billing

__all__ = [
    "FeatureNotEntitledError",
    "InsufficientBalanceError",
    "InsufficientCreditsError",
    "get_billing_service",
    "get_wallet_service",
    "register_billing",
    "register_wallet",
]
