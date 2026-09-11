"""向後相容：請改用 backend.billing.context。"""
from backend.billing.context import *  # noqa: F403

wallet_user_id = __import__("backend.billing.context", fromlist=["billing_user_id"]).billing_user_id
