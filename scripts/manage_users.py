"""CLI helpers to create or reset application users."""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from sqlalchemy import select
from sqlalchemy.orm import Session

from downloader_qbench_data.auth.passwords import (
    PasswordValidationError,
    hash_password,
)
from downloader_qbench_data.config import get_settings
from downloader_qbench_data.storage import session_scope
from downloader_qbench_data.storage.models import UserAccount


def _prompt_password(provided: str | None) -> str:
    if provided:
        return provided
    first = getpass.getpass("New password: ")
    second = getpass.getpass("Confirm password: ")
    if first != second:
        raise SystemExit("Passwords do not match.")
    return first


def _with_session(func: Callable[[argparse.Namespace, Session], None]) -> Callable[[argparse.Namespace], None]:
    def wrapper(args: argparse.Namespace) -> None:
        settings = get_settings()
        with session_scope(settings) as session:
            func(args, session)

    return wrapper


@_with_session
def create_user(args: argparse.Namespace, session: Session) -> None:
    username = args.username.strip()
    existing = session.scalar(select(UserAccount).where(UserAccount.username == username))
    if existing:
        raise SystemExit(f"User '{username}' already exists.")

    try:
        password = _prompt_password(args.password)
        password_hash = hash_password(password)
    except PasswordValidationError as exc:
        raise SystemExit(f"Password validation error: {exc}") from exc

    user = UserAccount(username=username, password_hash=password_hash)
    session.add(user)
    print(f"User '{username}' created successfully.")


@_with_session
def reset_password(args: argparse.Namespace, session: Session) -> None:
    username = args.username.strip()
    user = session.scalar(select(UserAccount).where(UserAccount.username == username))
    if not user:
        raise SystemExit(f"User '{username}' was not found.")

    try:
        password = _prompt_password(args.password)
        password_hash = hash_password(password)
    except PasswordValidationError as exc:
        raise SystemExit(f"Password validation error: {exc}") from exc

    user.password_hash = password_hash
    if args.unlock:
        user.failed_attempts = 0
        user.locked_until = None
    print(f"Password updated for '{username}'.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage dashboard users.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_cmd = subparsers.add_parser("create", help="Create a new user.")
    create_cmd.add_argument("--username", required=True, help="Unique username for the new user.")
    create_cmd.add_argument(
        "--password",
        help="Optional password value (otherwise prompted securely).",
    )
    create_cmd.set_defaults(func=create_user)

    reset_cmd = subparsers.add_parser("reset-password", help="Reset password for an existing user.")
    reset_cmd.add_argument("--username", required=True, help="Existing username.")
    reset_cmd.add_argument(
        "--password",
        help="Optional password value (otherwise prompted securely).",
    )
    reset_cmd.add_argument(
        "--unlock",
        action="store_true",
        help="Clear failed attempts and locked status while resetting the password.",
    )
    reset_cmd.set_defaults(func=reset_password)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = args.func
    handler(args)


if __name__ == "__main__":
    main(sys.argv[1:])
