"""Database engine and session helpers."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from downloader_qbench_data.config import AppSettings
from . import models

_engine: Engine | None = None
_session_factory: sessionmaker | None = None


def get_engine(settings: AppSettings) -> Engine:
    """Initialise (or reuse) the global SQLAlchemy engine."""

    global _engine
    if _engine is None:
        _engine = create_engine(
            settings.database.build_sqlalchemy_url(),
            future=True,
            pool_pre_ping=True,
        )
        models.Base.metadata.create_all(_engine)
    return _engine


def get_session_factory(settings: AppSettings) -> sessionmaker:
    """Return a session factory bound to the configured engine."""

    global _session_factory
    if _session_factory is None:
        engine = get_engine(settings)
        _session_factory = sessionmaker(
            bind=engine,
            autoflush=False,
            expire_on_commit=False,
            class_=Session,
        )
    return _session_factory


@contextmanager
def session_scope(settings: AppSettings) -> Iterator[Session]:
    """Provide a transactional scope."""

    factory = get_session_factory(settings)
    session: Session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
