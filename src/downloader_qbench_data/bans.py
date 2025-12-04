"""Helpers to manage banned entities."""

from __future__ import annotations

import time
from typing import Optional, Set, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from downloader_qbench_data.storage import BannedEntity

_CACHE_TTL_SECONDS = 300  # 5 minutes
_cache_expires_at: float = 0.0
_cache: Set[Tuple[str, int]] = set()


def _refresh_cache(session: Session) -> None:
    global _cache, _cache_expires_at
    rows = session.execute(select(BannedEntity.entity_type, BannedEntity.entity_id)).all()
    _cache = {(row.entity_type, int(row.entity_id)) for row in rows}
    _cache_expires_at = time.time() + _CACHE_TTL_SECONDS


def is_banned(session: Session, entity_type: str, entity_id: Optional[int]) -> bool:
    """Return True if the given entity is banned."""

    if entity_id is None:
        return False
    now = time.time()
    if now >= _cache_expires_at:
        _refresh_cache(session)
    return (entity_type, int(entity_id)) in _cache


def clear_ban_cache() -> None:
    """Force cache refresh on next call."""

    global _cache_expires_at
    _cache_expires_at = 0.0
