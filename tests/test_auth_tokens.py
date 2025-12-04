"""Tests for token utilities."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from downloader_qbench_data.auth.tokens import (
    TokenError,
    create_access_token,
    decode_access_token,
)
from downloader_qbench_data.config import AuthSettings


def test_create_and_decode_token_roundtrip() -> None:
    settings = AuthSettings(secret_key="unit-test-secret", token_ttl_hours=1)
    token, expires_at = create_access_token(settings, "tester")
    payload = decode_access_token(settings, token)
    assert payload["sub"] == "tester"
    assert expires_at > datetime.now(timezone.utc)


def test_decode_access_token_raises_when_expired() -> None:
    settings = AuthSettings(secret_key="unit-test-secret", token_ttl_hours=1)
    expired = datetime.now(timezone.utc) - timedelta(hours=1)
    token = jwt.encode(
        {"sub": "tester", "exp": int(expired.timestamp())},
        settings.secret_key,
        algorithm="HS256",
    )
    with pytest.raises(TokenError) as excinfo:
        decode_access_token(settings, token)
    assert excinfo.value.code == "token_expired"
