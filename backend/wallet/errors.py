"""向後相容。"""
from backend.billing.errors import *  # noqa: F403

InsufficientBalanceError = __import__(
    "backend.billing.errors", fromlist=["InsufficientCreditsError"]
).InsufficientCreditsError
