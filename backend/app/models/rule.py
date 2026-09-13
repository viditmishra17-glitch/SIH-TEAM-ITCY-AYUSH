"""
The configured rule set and its auditable results.

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


class Rule(Base):
    __tablename__ = "rules"

    rule_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    field_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rule_type: Mapped[str] = mapped_column(String(48))
    severity: Mapped[str] = mapped_column(String(16))
    explanation_template: Mapped[str] = mapped_column(Text)
    legal_reference: Mapped[str | None] = mapped_column(String(256), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class RuleResult(Base):
    __tablename__ = "rule_results"

    result_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.case_id", ondelete="CASCADE"), index=True
    )
    rule_id: Mapped[str] = mapped_column(String(32), index=True)
    field_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(20))
    severity: Mapped[str] = mapped_column(String(16))
    explanation: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    evidence_refs: Mapped[list | None] = mapped_column(JSON, nullable=True)
    ordinal: Mapped[int] = mapped_column(Integer, default=0)

    case: Mapped[Case] = relationship(back_populates="rule_results")


# ---------------------------------------------------------------------------
# evidence
# ---------------------------------------------------------------------------
