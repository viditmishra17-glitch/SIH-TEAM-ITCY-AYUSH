"""
SQLAlchemy ORM models — the frozen data contract (Build Manual section 4).

Every model is imported here so that SQLAlchemy's registry is complete before
any mapper is configured. Relationships reference each other by class name, so
importing only one module would leave those names unresolved.

Import from the package, not the individual modules:

    from app.models import Case, Evidence, RuleResult
"""

from app.models.base import Base, utcnow
from app.models.case import Case, CaseImage, Product, Report
from app.models.evidence import Evidence, ImageObservation
from app.models.rule import Rule, RuleResult
from app.models.source import (
    ListingField,
    ListingSnapshot,
    OfficialField,
    OfficialRecord,
)

__all__ = [
    "Base",
    "utcnow",
    "Case",
    "CaseImage",
    "Product",
    "Report",
    "Evidence",
    "ImageObservation",
    "Rule",
    "RuleResult",
    "ListingField",
    "ListingSnapshot",
    "OfficialField",
    "OfficialRecord",
]
