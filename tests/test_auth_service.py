"""Tests for authentication service logic."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from downloader_qbench_data.auth.passwords import hash_password
from downloader_qbench_data.auth.service import authenticate_user
from downloader_qbench_data.config import AuthSettings
from downloader_qbench_data.storage.models import UserAccount


def make_settings(hours: int = 3) -> SimpleNamespace:
    return SimpleNamespace(auth=AuthSettings(secret_key="unit-test-secret", token_ttl_hours=hours))


def test_authenticate_user_success_resets_counters():
    user = UserAccount(
        username="tester",
        password_hash=hash_password("ValidPass123"),
        failed_attempts=2,
        is_active=True,
    )
    session = MagicMock()
    session.scalar.return_value = user

    result = authenticate_user(session, make_settings(), "tester", "ValidPass123")

    assert result.success
    assert result.access_token is not None
    assert user.failed_attempts == 0
    assert user.locked_until is None
    session.add.assert_called_with(user)
    session.commit.assert_called()


def test_authenticate_user_invalid_password_increments_attempts():
    user = UserAccount(
        username="tester",
        password_hash=hash_password("ValidPass123"),
        failed_attempts=0,
        is_active=True,
    )
    session = MagicMock()
    session.scalar.return_value = user

    result = authenticate_user(session, make_settings(), "tester", "WrongPass123")

    assert not result.success
    assert user.failed_attempts == 1
    session.add.assert_called_with(user)
    session.commit.assert_called()


def test_authenticate_user_locks_after_three_attempts():
    user = UserAccount(
        username="tester",
        password_hash=hash_password("ValidPass123"),
        failed_attempts=2,
        is_active=True,
    )
    session = MagicMock()
    session.scalar.return_value = user

    result = authenticate_user(session, make_settings(), "tester", "WrongPass123")

    assert not result.success
    assert result.error == "locked"
    assert result.locked_until is not None
    assert user.failed_attempts == 0  # reset after locking
