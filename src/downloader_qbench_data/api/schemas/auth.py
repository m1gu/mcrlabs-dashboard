"""Schemas for authentication endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Input payload for login."""

    username: str = Field(..., min_length=3, max_length=150)
    password: str = Field(..., min_length=6)


class AuthenticatedUser(BaseModel):
    """Minimal representation of an authenticated user."""

    username: str


class TokenResponse(BaseModel):
    """Response returned after a successful login."""

    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    expires_in: int
    user: AuthenticatedUser
