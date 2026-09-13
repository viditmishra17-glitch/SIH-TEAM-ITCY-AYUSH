"""
OCR observations and the evidence attached to findings.

Part of the frozen data contract (Build Manual section 4). Deliberately
dialect-agnostic: the same models run on SQLite (local, offline demo, tests)
and on Supabase Postgres.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.models.base import Base, utcnow


class ImageObservation(Base):
    __tablename__ = "image_observations"

    obs_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    product_id: Mapped[str] = mapped_column(
        ForeignKey("products.product_id", ondelete="CASCADE"), index=True
    )
    image_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    field_name: Mapped[str] = mapped_column(String(64), index=True)
    value_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_norm: Mapped[dict | list | str | float | None] = mapped_column(JSON, nullable=True)
    bbox: Mapped[list | None] = mapped_column(JSON, nullable=True)  # [x, y, w, h]
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    engine: Mapped[str | None] = mapped_column(String(48), nullable=True)

    product: Mapped[Product] = relationship(back_populates="image_observations")


# ---------------------------------------------------------------------------
# listing_snapshots / listing_fields — seller evidence
# ---------------------------------------------------------------------------


class Evidence(Base):
    __tablename__ = "evidence"

    evidence_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.case_id", ondelete="CASCADE"), index=True
    )
    source_type: Mapped[str] = mapped_column(String(16))  # PHOTO / LISTING / OFFICIAL
    source_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    field_name: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    raw_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_value: Mapped[dict | list | str | float | None] = mapped_column(JSON, nullable=True)
    bbox: Mapped[list | None] = mapped_column(JSON, nullable=True)
    crop_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[dict | None] = mapped_column("metadata_json", JSON, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    case: Mapped[Case] = relationship(back_populates="evidence")


# ---------------------------------------------------------------------------
# case_images — bytes live in the DB, not on disk
# ---------------------------------------------------------------------------
