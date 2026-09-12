"""向後相容。"""
from backend.billing.errors import *

InsufficientBalanceError = __import__(
    "backend.billing.errors", fromlist=["InsufficientCreditsError"]
).InsufficientCreditsError
