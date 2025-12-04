"""Password hashing and validation helpers."""

from __future__ import annotations

import re

import bcrypt

_MIN_PASSWORD_LENGTH = 10
_RE_LOWER = re.compile(r"[a-z]")
_RE_UPPER = re.compile(r"[A-Z]")
_RE_DIGIT = re.compile(r"[0-9]")


class PasswordValidationError(ValueError):
    """Raised when a password does not satisfy the policy."""


def hash_password(password: str) -> str:
    """Hash a password using bcrypt after validating the policy."""

    _validate_password(password)
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    """Verify a password against a stored bcrypt hash."""

    if not hashed_password:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))
    except ValueError:
        return False


def _validate_password(password: str) -> None:
    """Ensure the password complies with the minimum policy."""

    if not password or len(password) < _MIN_PASSWORD_LENGTH:
        raise PasswordValidationError(
            f"Password must be at least {_MIN_PASSWORD_LENGTH} characters long."
        )
    if not _RE_LOWER.search(password):
        raise PasswordValidationError("Password must include at least one lowercase letter.")
    if not _RE_UPPER.search(password):
        raise PasswordValidationError("Password must include at least one uppercase letter.")
    if not _RE_DIGIT.search(password):
        raise PasswordValidationError("Password must include at least one digit.")

