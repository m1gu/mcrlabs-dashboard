"""JWT helper utilities."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Tuple

import jwt

from downloader_qbench_data.config import AuthSettings

_ALGORITHM = "HS256"


class TokenError(RuntimeError):
    """Raised when a token cannot be decoded or is invalid."""

    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code


def create_access_token(auth_settings: AuthSettings, subject: str) -> Tuple[str, datetime]:
    """Create a signed JWT for the given subject."""

    now = datetime.now(timezone.utc)
    ttl = max(int(auth_settings.token_ttl_hours), 1)
    expires_at = now + timedelta(hours=ttl)
    payload: Dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(payload, auth_settings.secret_key, algorithm=_ALGORITHM)
    return token, expires_at


def decode_access_token(auth_settings: AuthSettings, token: str) -> Dict[str, Any]:
    """Decode and validate the provided JWT."""

    try:
        return jwt.decode(
            token,
            auth_settings.secret_key,
            algorithms=[_ALGORITHM],
            options={"require": ["sub", "exp"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token expired.", "token_expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("Token is invalid.", "token_invalid") from exc
