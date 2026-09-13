"""
Pydantic schemas — the frozen API contract (Build Manual section 5).

The frontend is written against exactly these shapes. Fields may be *added*
without breaking consumers; renaming or removing one requires team agreement.
"""

from app.schemas.case import (
    CaseCreateResponse,
    CaseListItem,
    CaseListResponse,
    CaseResult,
    CaseSummaryCounts,
    EvidenceRef,
    FieldComparison,
    Finding,
    HealthResponse,
    ImageInfo,
    LayerValue,
    ProductInfo,
    SourceStatus,
)

__all__ = [
    "CaseCreateResponse",
    "CaseListItem",
    "CaseListResponse",
    "CaseResult",
    "CaseSummaryCounts",
    "EvidenceRef",
    "FieldComparison",
    "Finding",
    "HealthResponse",
    "ImageInfo",
    "LayerValue",
    "ProductInfo",
    "SourceStatus",
]
