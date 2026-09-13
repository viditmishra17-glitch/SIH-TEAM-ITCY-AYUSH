"""
Seller-listing and official-registry evidence snapshots.

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


class ListingSnapshot(Base):
    __tablename__ = "listing_snapshots"

    snapshot_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    product_id: Mapped[str] = mapped_column(
        ForeignKey("products.product_id", ondelete="CASCADE"), index=True
    )
    source: Mapped[str] = mapped_column(String(64))
    url_or_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    is_live: Mapped[bool] = mapped_column(Boolean, default=False)
    raw_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    product: Mapped[Product] = relationship(back_populates="listing_snapshots")
    fields: Mapped[list["ListingField"]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )


class ListingField(Base):
    __tablename__ = "listing_fields"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("listing_snapshots.snapshot_id", ondelete="CASCADE"), index=True
    )
    field_name: Mapped[str] = mapped_column(String(64), index=True)
    value_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_norm: Mapped[dict | list | str | float | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)

    snapshot: Mapped[ListingSnapshot] = relationship(back_populates="fields")


# ---------------------------------------------------------------------------
# official_records / official_fields — e-Maap / CLMS evidence
# ---------------------------------------------------------------------------


class OfficialRecord(Base):
    __tablename__ = "official_records"

    record_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    product_id: Mapped[str] = mapped_column(
        ForeignKey("products.product_id", ondelete="CASCADE"), index=True
    )
    source: Mapped[str] = mapped_column(String(64))
    url_or_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    is_live: Mapped[bool] = mapped_column(Boolean, default=False)
    raw_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    product: Mapped[Product] = relationship(back_populates="official_records")
    fields: Mapped[list["OfficialField"]] = relationship(
        back_populates="record", cascade="all, delete-orphan"
    )


class OfficialField(Base):
    __tablename__ = "official_fields"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    record_id: Mapped[str] = mapped_column(
        ForeignKey("official_records.record_id", ondelete="CASCADE"), index=True
    )
    field_name: Mapped[str] = mapped_column(String(64), index=True)
    value_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_norm: Mapped[dict | list | str | float | None] = mapped_column(JSON, nullable=True)

    record: Mapped[OfficialRecord] = relationship(back_populates="fields")


# ---------------------------------------------------------------------------
# rules / rule_results
# ---------------------------------------------------------------------------
