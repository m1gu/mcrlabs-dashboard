"""Authentication routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from downloader_qbench_data.auth.service import authenticate_user
from downloader_qbench_data.api.schemas.auth import (
    AuthenticatedUser,
    LoginRequest,
    TokenResponse,
)
from downloader_qbench_data.config import AppSettings

from ..dependencies import get_app_settings, get_db_session

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    session: Session = Depends(get_db_session),
    settings: AppSettings = Depends(get_app_settings),
) -> TokenResponse:
    """Return a bearer token for valid credentials."""

    result = authenticate_user(session, settings, payload.username, payload.password)
    if not result.success or not result.access_token or not result.expires_at or not result.user:
        if result.error == "locked":
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail={
                    "error": "account_locked",
                    "locked_until": result.locked_until.isoformat() if result.locked_until else None,
                },
            )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_credentials")

    expires_in_seconds = int(max(settings.auth.token_ttl_hours, 1) * 3600)
    return TokenResponse(
        access_token=result.access_token,
        expires_at=result.expires_at,
        expires_in=expires_in_seconds,
        user=AuthenticatedUser(username=result.user.username),
    )
