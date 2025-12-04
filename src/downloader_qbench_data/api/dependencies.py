"""Shared dependency providers for the FastAPI layer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Generator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from downloader_qbench_data.auth.tokens import TokenError, decode_access_token
from downloader_qbench_data.config import AppSettings, get_settings
from downloader_qbench_data.storage import UserAccount, get_session_factory

_bearer_scheme = HTTPBearer(auto_error=False)


def get_app_settings() -> AppSettings:
    """Return cached application settings."""

    return get_settings()


def get_db_session(settings: AppSettings = Depends(get_app_settings)) -> Generator[Session, None, None]:
    """Provide a SQLAlchemy session scoped to the request lifecycle."""

    session_factory = get_session_factory(settings)
    session: Session = session_factory()
    try:
        yield session
    finally:
        session.close()


def require_active_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    settings: AppSettings = Depends(get_app_settings),
    session: Session = Depends(get_db_session),
) -> UserAccount:
    """Ensure the requester has supplied a valid bearer token."""

    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not_authenticated")

    token = credentials.credentials
    try:
        payload = decode_access_token(settings.auth, token)
    except TokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=exc.code) from exc

    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_token_payload")

    user = session.scalar(select(UserAccount).where(UserAccount.username == username))
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user_not_found")

    now = datetime.now(timezone.utc)
    if user.locked_until and user.locked_until > now:
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="account_locked")

    return user
