"""
API contract — FROZEN AT H0 (Build Manual section 5).

The frontend is written against exactly this shape. Fields may be *added*
without breaking consumers; renaming or removing one requires team agreement.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class LayerValue(BaseModel):
    """One layer's view of one field."""

    available: bool = False
    raw: str | None = None
    norm: Any | None = None
    display: str | None = None
    confidence: float | None = None
    evidence_id: str | None = None
    bbox: list[float] | None = None


class FieldComparison(BaseModel):
    field_name: str
    label: str
    photo: LayerValue = Field(default_factory=LayerValue)
    listing: LayerValue = Field(default_factory=LayerValue)
    official: LayerValue = Field(default_factory=LayerValue)
    status: str = "NOT_APPLICABLE"
    note: str | None = None
    is_material: bool = False


class Finding(BaseModel):
    rule_id: str
    field_name: str | None = None
    severity: str
    status: str
    explanation: str
    confidence: float = 0.0
    evidence_ids: list[str] = Field(default_factory=list)
    legal_reference: str | None = None


class SourceStatus(BaseModel):
    available: bool = False
    source: str | None = None
    reference: str | None = None
    captured_at: datetime | None = None
    is_live: bool = False
    note: str | None = None


class EvidenceRef(BaseModel):
    evidence_id: str
    source_type: str
    field_name: str | None = None
    raw_value: str | None = None
    normalized_value: Any | None = None
    display: str | None = None
    confidence: float = 1.0
    bbox: list[float] | None = None
    has_crop: bool = False
    crop_url: str | None = None
    excerpt: str | None = None
    source_ref: str | None = None
    captured_at: datetime | None = None
    metadata: dict[str, Any] | None = None


class ProductInfo(BaseModel):
    product_id: str | None = None
    name: str | None = None
    brand: str | None = None
    category: str | None = None
    identifier: str | None = None


class CaseSummaryCounts(BaseModel):
    passed: int = 0
    failed: int = 0
    review: int = 0
    not_applicable: int = 0
    high_severity_failures: int = 0
    fields_compared: int = 0
    fields_mismatched: int = 0


class ImageInfo(BaseModel):
    image_id: str
    kind: str
    width: int
    height: int
    url: str
    quality_score: float | None = None


class CaseResult(BaseModel):
    """The single response shape the whole frontend is built against."""

    case_id: str
    status: str
    classification: str | None = None
    overall_confidence: float | None = None
    headline: str | None = None
    created_at: datetime | None = None
    verified_at: datetime | None = None
    ruleset_version: str | None = None
    is_golden: bool = False
    product: ProductInfo = Field(default_factory=ProductInfo)
    sources: dict[str, SourceStatus] = Field(default_factory=dict)
    images: list[ImageInfo] = Field(default_factory=list)
    fields: dict[str, FieldComparison] = Field(default_factory=dict)
    field_order: list[str] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    summary: CaseSummaryCounts = Field(default_factory=CaseSummaryCounts)
    disclaimer: str = (
        "Engineering triage output. Evidence and configured rules are shown in full; "
        "a qualified officer remains responsible for any enforcement action."
    )


class CaseListItem(BaseModel):
    case_id: str
    created_at: datetime | None = None
    status: str
    classification: str | None = None
    overall_confidence: float | None = None
    product_name: str | None = None
    brand: str | None = None
    identifier: str | None = None
    top_severity: str | None = None
    failed_rules: int = 0
    review_rules: int = 0
    is_golden: bool = False


class CaseListResponse(BaseModel):
    total: int
    items: list[CaseListItem]


class CaseCreateResponse(BaseModel):
    case_id: str
    status: str
    classification: str | None = None
    message: str


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
    database: str
    database_ok: bool
    ocr_engine: str
    live_sources_enabled: bool
    ruleset_version: str
    golden_cases: int
    offline_ready: bool
