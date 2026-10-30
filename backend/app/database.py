"""SQLAlchemy engine/session setup with PostgreSQL support and SQLite fallback."""
from __future__ import annotations

import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def _build_engine():
    url = settings.database_url
    kwargs: dict = {"pool_pre_ping": True, "future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    try:
        engine = create_engine(url, **kwargs)
        # Verify connectivity early so failures produce a clear log line.
        with engine.connect():
            pass
        logger.info("Database connected: %s", _safe_url(url))
        return engine
    except Exception as exc:  # pragma: no cover - depends on environment
        if url.startswith("sqlite"):
            raise
        logger.error(
            "Configured database unavailable (%s); falling back to SQLite. Error: %s",
            _safe_url(url),
            exc,
        )
        fallback = f"sqlite:///{settings.data_dir / 'smdpis.db'}"
        settings.ensure_dirs()
        return create_engine(
            fallback, connect_args={"check_same_thread": False}, future=True
        )


def _safe_url(url: str) -> str:
    """Strip credentials from a database URL for logging."""
    if "@" in url and "://" in url:
        head, tail = url.split("://", 1)
        if "@" in tail:
            tail = tail.split("@", 1)[1]
            return f"{head}://***@{tail}"
    return url


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db():
    """FastAPI dependency yielding a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables if they do not exist."""
    settings.ensure_dirs()
    from app import models  # noqa: F401  (registers models)

    Base.metadata.create_all(bind=engine)
