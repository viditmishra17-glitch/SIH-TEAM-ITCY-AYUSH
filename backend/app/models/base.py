"""Declarative base and shared column helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import DeclarativeBase


def utcnow() -> datetime:
    """Timezone-aware UTC timestamp (naive datetimes cause silent bugs)."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass
