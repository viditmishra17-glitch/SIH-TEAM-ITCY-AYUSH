"""
Engine / session factory.

Handles the three environments the project actually runs in:

* SQLite file       — local dev, offline demo, CI (default, zero setup)
* SQLite in-memory  — tests
* Supabase Postgres — production on Render

The Supabase specifics matter and are easy to get wrong:

* Supabase hands out ``postgresql://`` URLs; SQLAlchemy 2 needs a driver, so
  we rewrite them to ``postgresql+psycopg://``.
* The pooled connection string (port 6543) goes through PgBouncer in
  *transaction* mode, which cannot hold server-side prepared statements. We
  therefore disable SQLAlchemy's own pooling (NullPool) and turn off psycopg's
  prepared-statement cache. Without this you get random
  ``DuplicatePreparedStatement`` errors under load.
* TLS is required, so ``sslmode=require`` is added when absent.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

from app.core import config
from app.models import Base

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def normalize_database_url(url: str) -> str:
    """Make a raw DATABASE_URL safe for SQLAlchemy 2 + Supabase."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]

    if not url.startswith("postgresql+psycopg://"):
        return url

    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.setdefault("sslmode", "require")
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


def _is_pgbouncer(url: str) -> bool:
    """Supabase's transaction-mode pooler listens on 6543."""
    parts = urlsplit(url)
    if parts.port == 6543:
        return True
    return "pgbouncer=true" in url.lower()


def build_engine(url: str | None = None) -> Engine:
    """Create a correctly-configured engine for the given URL."""
    raw = url or config.DATABASE_URL
    normalized = normalize_database_url(raw)

    if normalized.startswith("sqlite"):
        if ":memory:" in normalized:
            # One shared connection, or each session sees an empty database.
            return create_engine(
                normalized,
                echo=config.SQL_ECHO,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
        return create_engine(
            normalized,
            echo=config.SQL_ECHO,
            connect_args={"check_same_thread": False},
        )

    if _is_pgbouncer(normalized):
        return create_engine(
            normalized,
            echo=config.SQL_ECHO,
            poolclass=NullPool,
            # psycopg3: never use server-side prepared statements behind
            # PgBouncer transaction pooling.
            connect_args={"prepare_threshold": None},
        )

    return create_engine(
        normalized,
        echo=config.SQL_ECHO,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_recycle=1800,
    )


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = build_engine()
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(), autoflush=False, expire_on_commit=False
        )
    return _SessionLocal


def configure(url: str) -> None:
    """Point the whole process at a different database (used by tests)."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = build_engine(url)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)


def init_db(drop: bool = False) -> None:
    """Create tables. Idempotent."""
    engine = get_engine()
    if drop:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope for scripts and background work."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
