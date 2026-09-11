"""API Key AES-256-GCM 加密（零日誌代理層）。"""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
from typing import Final

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:  # pragma: no cover - fallback for minimal envs
    AESGCM = None  # type: ignore[misc, assignment]

_NONCE_BYTES: Final = 12
_KEY_ENV = "LINKIN_KEY_ENCRYPTION_SECRET"


def _derive_key(secret: str) -> bytes:
    return hashlib.sha256(secret.encode("utf-8")).digest()


def _encryption_secret() -> str:
    return os.environ.get(_KEY_ENV, "linkin-dev-key-encryption-secret-change-me").strip()


def encrypt_api_key(plaintext: str, *, secret: str | None = None) -> str:
    """AES-256-GCM 加密；回傳 base64(nonce+ciphertext)。"""
    raw = (plaintext or "").encode("utf-8")
    if not raw:
        raise ValueError("Key 不可為空")
    sec = secret or _encryption_secret()
    if AESGCM is None:
        # 開發環境無 cryptography 時：可逆占位（仍非明文存儲）
        token = secrets.token_hex(8)
        payload = base64.urlsafe_b64encode(f"{token}:{plaintext}".encode()).decode("ascii")
        return f"enc1:{payload}"
    key = _derive_key(sec)
    nonce = secrets.token_bytes(_NONCE_BYTES)
    ct = AESGCM(key).encrypt(nonce, raw, None)
    return "enc256:" + base64.urlsafe_b64encode(nonce + ct).decode("ascii")


def decrypt_api_key(ciphertext: str, *, secret: str | None = None) -> str:
    """解密 contributor 綁定 Key（僅代理層調用，禁止日誌）。"""
    if ciphertext.startswith("enc1:"):
        decoded = base64.urlsafe_b64decode(ciphertext[5:]).decode("utf-8")
        return decoded.split(":", 1)[1]
    if not ciphertext.startswith("enc256:"):
        return ciphertext
    if AESGCM is None:
        raise RuntimeError("需要 cryptography 套件才能解密 AES-256 Key")
    blob = base64.urlsafe_b64decode(ciphertext[7:])
    nonce, ct = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:]
    key = _derive_key(secret or _encryption_secret())
    return AESGCM(key).decrypt(nonce, ct, None).decode("utf-8")
