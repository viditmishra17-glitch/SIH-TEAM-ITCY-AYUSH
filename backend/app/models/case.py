"""
Case, product identity, stored images and generated reports.

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


class Case(Base):
    __tablename__ = "cases"

    case_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="CREATED")
    classification: Mapped[str | None] = mapped_column(String(40), nullable=True)
    overall_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    headline: Mapped[str | None] = mapped_column(Text, nullable=True)
    ruleset_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_golden: Mapped[bool] = mapped_column(Boolean, default=False)
    #: Why a layer was unavailable, keyed by PHOTO/LISTING/OFFICIAL. Kept so a
    #: re-verification can reproduce the same "source missing" reasoning.
    source_notes: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    extraction_notes: Mapped[list | None] = mapped_column(JSON, nullable=True)

    product: Mapped["Product | None"] = relationship(
        back_populates="case", uselist=False, cascade="all, delete-orphan"
    )
    rule_results: Mapped[list["RuleResult"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )
    evidence: Mapped[list["Evidence"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )
    images: Mapped[list["CaseImage"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )
    reports: Mapped[list["Report"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# products
# ---------------------------------------------------------------------------


class Product(Base):
    __tablename__ = "products"

    product_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.case_id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(128), nullable=True)
    category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    identifier: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    case: Mapped[Case] = relationship(back_populates="product")
    image_observations: Mapped[list["ImageObservation"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    listing_snapshots: Mapped[list["ListingSnapshot"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    official_records: Mapped[list["OfficialRecord"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# image_observations — OCR/CV extraction with visual provenance
# ---------------------------------------------------------------------------


class CaseImage(Base):
    """Original and derived image bytes.

    Stored in the database on purpose: Render's filesystem is ephemeral, so a
    case that survives a restart must not depend on local files.
    """

    __tablename__ = "case_images"

    image_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.case_id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16))  # ORIGINAL / PREPROCESSED
    filename: Mapped[str | None] = mapped_column(String(256), nullable=True)
    content_type: Mapped[str] = mapped_column(String(64), default="image/png")
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)

    case: Mapped[Case] = relationship(back_populates="images")


# ---------------------------------------------------------------------------
# reports
# ---------------------------------------------------------------------------


class Report(Base):
    __tablename__ = "reports"

    report_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.case_id", ondelete="CASCADE"), index=True
    )
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    fmt: Mapped[str] = mapped_column(String(16), default="html")
    file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)

    case: Mapped[Case] = relationship(back_populates="reports")
