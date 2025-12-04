"""CLI helpers to add or remove banned entities."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from downloader_qbench_data.config import get_settings
from downloader_qbench_data.storage import BannedEntity, session_scope
from downloader_qbench_data.bans import clear_ban_cache

VALID_TYPES = {"customer", "order", "sample", "batch", "test"}


def _with_session(func: Callable[[argparse.Namespace, Session], None]) -> Callable[[argparse.Namespace], None]:
    def wrapper(args: argparse.Namespace) -> None:
        settings = get_settings()
        with session_scope(settings) as session:
            func(args, session)
            clear_ban_cache()

    return wrapper


@_with_session
def add_ban(args: argparse.Namespace, session: Session) -> None:
    entity_type = args.type.lower()
    if entity_type not in VALID_TYPES:
        raise SystemExit(f"Unsupported entity type '{entity_type}'. Allowed: {', '.join(sorted(VALID_TYPES))}")
    entity_id = int(args.id)
    existing = session.scalar(
        select(BannedEntity).where(BannedEntity.entity_type == entity_type, BannedEntity.entity_id == entity_id)
    )
    if existing:
        print(f"{entity_type} {entity_id} is already banned.")
        return
    session.execute(
        insert(BannedEntity).values(entity_type=entity_type, entity_id=entity_id, reason=args.reason or None)
    )
    print(f"Banned {entity_type} {entity_id}.")


@_with_session
def remove_ban(args: argparse.Namespace, session: Session) -> None:
    entity_type = args.type.lower()
    if entity_type not in VALID_TYPES:
        raise SystemExit(f"Unsupported entity type '{entity_type}'. Allowed: {', '.join(sorted(VALID_TYPES))}")
    entity_id = int(args.id)
    result = session.execute(
        delete(BannedEntity).where(BannedEntity.entity_type == entity_type, BannedEntity.entity_id == entity_id)
    )
    if result.rowcount:
        print(f"Unbanned {entity_type} {entity_id}.")
    else:
        print(f"No ban entry found for {entity_type} {entity_id}.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage banned entities.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_cmd = subparsers.add_parser("add", help="Ban an entity.")
    add_cmd.add_argument("--type", required=True, help="Entity type (customer|order|sample|batch|test).")
    add_cmd.add_argument("--id", required=True, help="Entity ID.")
    add_cmd.add_argument("--reason", help="Optional reason for the ban.")
    add_cmd.set_defaults(func=add_ban)

    remove_cmd = subparsers.add_parser("remove", help="Remove an entity from the ban list.")
    remove_cmd.add_argument("--type", required=True, help="Entity type (customer|order|sample|batch|test).")
    remove_cmd.add_argument("--id", required=True, help="Entity ID.")
    remove_cmd.set_defaults(func=remove_ban)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = args.func
    handler(args)


if __name__ == "__main__":
    main(sys.argv[1:])
