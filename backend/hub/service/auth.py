"""Hub API 身份驗證（自 backend.hub.service 抽出）。"""

from __future__ import annotations

from backend.hub.errors import HubError
from backend.hub.runtime import runtime
from backend.hub.store import HubUser


def authenticate(authorization: str | None) -> HubUser:
    """驗證 Bearer Token。
    
    支援兩種認證方式：
    1. API Key: Bearer <api_key> - 從 store 中查找匹配的用戶
    2. JWT Token: Bearer <jwt_token> - 驗證 JWT 簽名和過期時間
    
    增強驗證邏輯：
    - 嚴格檢查 Authorization header 格式
    - 防止空白或過短的 token
    - 對 JWT token 進行完整的簽名和過期驗證
    """
    import base64
    import hashlib
    import hmac
    import json
    import time
    
    if not authorization:
        raise HubError(401, "UNAUTHORIZED", "缺少 Authorization header")
    
    if not authorization.startswith("Bearer "):
        raise HubError(401, "UNAUTHORIZED", "Authorization header 必須以 Bearer 開頭")
    
    token = authorization[7:].strip()
    
    if not token or len(token) < 10:
        raise HubError(401, "UNAUTHORIZED", "Token 長度不足")
    
    # 檢查是否為 JWT token (包含三個部分，以 . 分隔)
    if token.count(".") == 2:
        # JWT token 驗證
        try:
            header_b, body_b, sig_b = token.split(".")
            
            # 填充 base64url
            pad = "=" * (-len(body_b) % 4)
            header_pad = "=" * (-len(header_b) % 4)
            
            # 解碼 payload 獲取過期時間
            try:
                payload = json.loads(base64.urlsafe_b64decode(body_b + pad))
            except Exception as exc:
                raise HubError(401, "UNAUTHORIZED", "JWT payload 解析失敗") from exc
            
            # 驗證過期時間
            now = int(time.time())
            exp = payload.get("exp", 0)
            iat = payload.get("iat", 0)
            
            if exp and exp < now:
                raise HubError(401, "UNAUTHORIZED", "JWT token 已過期")
            
            if iat and (now - iat) > 86400:  # 超過 24 小時
                raise HubError(401, "UNAUTHORIZED", "JWT token 簽發時間過久")
            
            # 驗證簽名
            from backend.hub.tools import JWT_SECRET
            expected_sig = base64.urlsafe_b64encode(
                hmac.new(JWT_SECRET, f"{header_b}.{body_b}".encode(), hashlib.sha256).digest()
            ).rstrip(b"=").decode("ascii")
            
            if not hmac.compare_digest(expected_sig, sig_b):
                raise HubError(401, "UNAUTHORIZED", "JWT 簽名驗證失敗")
            
            # 從 JWT 中提取用戶 ID
            user_id = payload.get("sub")
            if not user_id:
                raise HubError(401, "UNAUTHORIZED", "JWT 缺少用戶標識")
            
            # 創建臨時用戶對象（實際應用中應從數據庫加載）
            from uuid import UUID
            user = HubUser(
                id=UUID(user_id) if isinstance(user_id, str) else user_id,
                name=payload.get("name", "jwt-user"),
                api_key_hash="",
                daily_budget_limit_usd=payload.get("daily_budget", 10.0),
            )
            return user
            
        except HubError:
            raise
        except Exception as exc:
            raise HubError(401, "UNAUTHORIZED", f"JWT 驗證失敗：{exc}") from exc
    
    # API Key 驗證（原有邏輯）
    if not (43 <= len(token) <= 128):
        # 開發金鑰較短時仍允許精確命中 store
        short_key_user = runtime.store.get_by_api_key(token)
        if short_key_user:
            return short_key_user
        raise HubError(401, "UNAUTHORIZED", "缺少或無效的 API Key")
    
    api_user = runtime.store.get_by_api_key(token)
    if api_user is None:
        raise HubError(401, "UNAUTHORIZED", "缺少或無效的 API Key")
    return api_user
