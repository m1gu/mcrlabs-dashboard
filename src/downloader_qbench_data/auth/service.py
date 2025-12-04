"""User authentication service helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from downloader_qbench_data.config import AppSettings
from downloader_qbench_data.storage import UserAccount

from .passwords import verify_password
from .tokens import create_access_token

_MAX_FAILED_ATTEMPTS = 3
_LOCKOUT_DURATION = timedelta(hours=24)


@dataclass
class AuthResult:
    """Represents the outcome of an authentication attempt."""

    success: bool
    user: Optional[UserAccount] = None
    access_token: Optional[str] = None
    expires_at: Optional[datetime] = None
    error: Optional[str] = None
    locked_until: Optional[datetime] = None


def authenticate_user(session: Session, settings: AppSettings, username: str, password: str) -> AuthResult:
    """Validate credentials and issue an access token when successful."""

    user = session.scalar(select(UserAccount).where(UserAccount.username == username))
    now = datetime.now(timezone.utc)
    if not user or not user.is_active:
        return _failed_result(session, user, now, "invalid_credentials")

    if user.locked_until and user.locked_until > now:
        return AuthResult(False, user=user, error="locked", locked_until=user.locked_until)

    if not verify_password(password, user.password_hash):
        return _failed_result(session, user, now, "invalid_credentials")

    token, expires_at = create_access_token(settings.auth, user.username)
    user.failed_attempts = 0
    user.locked_until = None
    user.last_login_at = now
    session.add(user)
    session.commit()
    return AuthResult(True, user=user, access_token=token, expires_at=expires_at)


def _failed_result(session: Session, user: Optional[UserAccount], now: datetime, error: str) -> AuthResult:
    if user:
        user.failed_attempts = (user.failed_attempts or 0) + 1
        if user.failed_attempts >= _MAX_FAILED_ATTEMPTS:
            user.locked_until = now + _LOCKOUT_DURATION
            user.failed_attempts = 0
        session.add(user)
        session.commit()
        is_locked = user.locked_until is not None and user.locked_until > now
        return AuthResult(
            False,
            user=user,
            error="locked" if is_locked else error,
            locked_until=user.locked_until if is_locked else None,
        )
    return AuthResult(False, error=error)
