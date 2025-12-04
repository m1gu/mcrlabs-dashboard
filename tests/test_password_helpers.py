"""Tests for password hashing helpers."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from downloader_qbench_data.auth.passwords import (
    PasswordValidationError,
    hash_password,
    verify_password,
)


def test_hash_and_verify_password_roundtrip() -> None:
    password = "ValidPass123"
    hashed = hash_password(password)
    assert hashed != password
    assert verify_password(password, hashed)
    assert not verify_password("WrongPass123", hashed)


@pytest.mark.parametrize(
    "password",
    [
        "",
        "short1A",
        "alllowercase123",
        "ALLUPPERCASE123",
        "NoDigitsHere",
    ],
)
def test_hash_password_validation(password: str) -> None:
    with pytest.raises(PasswordValidationError):
        hash_password(password)
