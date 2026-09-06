"""Password hashing, JWT tokens and credential encryption for the hub."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import bcrypt
from cryptography.fernet import Fernet, InvalidToken
from jose import JWTError, jwt

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    """Hash a password with bcrypt (bcrypt caps input at 72 bytes)."""
    raw = password.encode("utf-8")[:72]
    return bcrypt.hashpw(raw, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time password check."""
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: str, secret_key: str, ttl_days: int = 30, extra: Optional[Dict[str, Any]] = None) -> str:
    """Create a signed JWT for a user."""
    payload: Dict[str, Any] = {
        "sub": user_id,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(days=ttl_days),
        "scope": "hub",
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str, secret_key: str) -> Optional[str]:
    """Return the user id encoded in a token, or None if invalid/expired."""
    try:
        payload = jwt.decode(token, secret_key, algorithms=[ALGORITHM])
    except JWTError:
        return None
    sub = payload.get("sub")
    return str(sub) if sub else None


class CredentialVault:
    """Encrypts/decrypts JSON credential blobs with Fernet (AES-128-CBC + HMAC)."""

    def __init__(self, key: bytes):
        self._fernet = Fernet(key)

    def encrypt(self, data: Optional[Dict[str, Any]]) -> Optional[str]:
        """Encrypt a dict; empty/None -> None."""
        if not data:
            return None
        return self._fernet.encrypt(json.dumps(data, separators=(",", ":")).encode("utf-8")).decode("utf-8")

    def decrypt(self, blob: Optional[str]) -> Dict[str, Any]:
        """Decrypt a blob; None/invalid -> {}."""
        if not blob:
            return {}
        try:
            return json.loads(self._fernet.decrypt(blob.encode("utf-8")).decode("utf-8"))
        except (InvalidToken, ValueError):
            return {}
