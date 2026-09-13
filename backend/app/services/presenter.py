"""
Turn a persisted case into the frozen API response shape.

Kept separate from the routers so the report generator and the tests can build
exactly the same structure the UI sees — the report is a *rendering* of the
case, never a second decision engine (Build Manual section 20, step 10).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Case, CaseImage, Evidence, RuleResult
from app.engine.reconcile import _field_outcome  # noqa: PLC2701 - intentional reuse
from app.engine.rules import LISTING, OFFICIAL, PHOTO
from app.schemas.case import (
    CaseListItem,
    CaseResult,
    CaseSummaryCounts,
    EvidenceRef,
    FieldComparison,
    Finding,
    ImageInfo,
    LayerValue,
    ProductInfo,
    SourceStatus,
)
from app.engine.vocabulary import (
    CANONICAL_FIELDS,
    FIELD_LABELS,
    FieldStatus,
    MATERIAL_FIELDS,
    RuleStatus,
    SEVERITY_ORDER,
)
from app.services.case_service import _load_layers
from app.pipeline.normalize import display_field

#: Fields the officer UI shows as columns, in demo-priority order.
DISPLAY_ORDER: tuple[str, ...] = (
    "mrp",
    "net_quantity",
    "manufacturer_name",
    "packer_name",
    "importer_name",
    "product_name",
    "brand",
    "identifier",
    "manufacturing_date",
    "packing_date",
    "expiry_date",
    "consumer_care",
)


def _layer_value(value, field_name: str) -> LayerValue:
    if value is None:
        return LayerValue(available=False)
    return LayerValue(
        available=True,
        raw=value.raw,
        norm=value.norm,
        display=display_field(field_name, value.norm) or value.raw,
        confidence=round(float(value.confidence), 4),
        evidence_id=value.evidence_id,
        bbox=value.bbox,
    )


def build_case_result(session: Session, case: Case) -> CaseResult:
    """Assemble the complete, frozen result payload for one case."""
    layers, _ = _load_layers(session, case)

    rule_results = (
        session.execute(
            select(RuleResult)
            .where(RuleResult.case_id == case.case_id)
            .order_by(RuleResult.ordinal)
        )
        .scalars()
        .all()
    )
    evidence_rows = (
        session.execute(
            select(Evidence)
            .where(Evidence.case_id == case.case_id)
            .order_by(Evidence.evidence_id)
        )
        .scalars()
        .all()
    )
    images = (
        session.execute(
            select(CaseImage)
            .where(CaseImage.case_id == case.case_id)
            .order_by(CaseImage.image_id)
        )
        .scalars()
        .all()
    )

    fields: dict[str, FieldComparison] = {}
    order: list[str] = []
    for name in DISPLAY_ORDER + tuple(
        f for f in CANONICAL_FIELDS if f not in DISPLAY_ORDER
    ):
        photo = layers[PHOTO].get(name)
        listing = layers[LISTING].get(name)
        official = layers[OFFICIAL].get(name)
        if photo is None and listing is None and official is None:
            continue
        outcome = _field_outcome(name, layers)
        fields[name] = FieldComparison(
            field_name=name,
            label=FIELD_LABELS.get(name, name),
            photo=_layer_value(photo, name),
            listing=_layer_value(listing, name),
            official=_layer_value(official, name),
            status=outcome.status,
            note=outcome.note,
            is_material=name in MATERIAL_FIELDS,
        )
        order.append(name)

    findings = [
        Finding(
            rule_id=row.rule_id,
            field_name=row.field_name,
            severity=row.severity,
            status=row.status,
            explanation=row.explanation,
            confidence=round(float(row.confidence or 0.0), 4),
            evidence_ids=list(row.evidence_refs or []),
        )
        for row in rule_results
    ]

    evidence = [
        EvidenceRef(
            evidence_id=row.evidence_id,
            source_type=row.source_type,
            field_name=row.field_name,
            raw_value=row.raw_value,
            normalized_value=row.normalized_value,
            display=display_field(row.field_name or "", row.normalized_value)
            if isinstance(row.normalized_value, dict)
            else row.raw_value,
            confidence=round(float(row.confidence or 0.0), 4),
            bbox=row.bbox,
            has_crop=bool(row.bbox) and row.source_type == PHOTO,
            crop_url=(
                f"/cases/{case.case_id}/evidence/{row.evidence_id}/crop"
                if row.bbox and row.source_type == PHOTO
                else None
            ),
            excerpt=row.excerpt,
            source_ref=row.source_ref,
            captured_at=row.captured_at,
            metadata=row.meta,
        )
        for row in evidence_rows
    ]

    sources = {
        key: SourceStatus(
            available=layer.available,
            source=layer.source,
            reference=layer.reference,
            captured_at=layer.captured_at,
            is_live=layer.is_live,
            note=layer.reason,
        )
        for key, layer in layers.items()
    }

    summary = CaseSummaryCounts(
        passed=sum(1 for f in findings if f.status == RuleStatus.PASS.value),
        failed=sum(1 for f in findings if f.status == RuleStatus.FAIL.value),
        review=sum(1 for f in findings if f.status == RuleStatus.REVIEW.value),
        not_applicable=sum(
            1 for f in findings if f.status == RuleStatus.NOT_APPLICABLE.value
        ),
        high_severity_failures=sum(
            1
            for f in findings
            if f.status == RuleStatus.FAIL.value and f.severity == "HIGH"
        ),
        fields_compared=sum(
            1
            for f in fields.values()
            if f.status in {FieldStatus.MATCH.value, FieldStatus.MISMATCH.value}
        ),
        fields_mismatched=sum(
            1 for f in fields.values() if f.status == FieldStatus.MISMATCH.value
        ),
    )

    return CaseResult(
        case_id=case.case_id,
        status=case.status,
        classification=case.classification,
        overall_confidence=case.overall_confidence,
        headline=case.headline,
        created_at=case.created_at,
        verified_at=case.verified_at,
        ruleset_version=case.ruleset_version,
        is_golden=bool(case.is_golden),
        product=ProductInfo(
            product_id=case.product.product_id if case.product else None,
            name=case.product.name if case.product else None,
            brand=case.product.brand if case.product else None,
            category=case.product.category if case.product else None,
            identifier=case.product.identifier if case.product else None,
        ),
        sources=sources,
        images=[
            ImageInfo(
                image_id=img.image_id,
                kind=img.kind,
                width=img.width,
                height=img.height,
                quality_score=img.quality_score,
                url=f"/cases/{case.case_id}/images/{img.image_id}",
            )
            for img in images
        ],
        fields=fields,
        field_order=order,
        findings=findings,
        evidence=evidence,
        summary=summary,
    )


def build_list_item(session: Session, case: Case) -> CaseListItem:
    rows = (
        session.execute(select(RuleResult).where(RuleResult.case_id == case.case_id))
        .scalars()
        .all()
    )
    failed = [r for r in rows if r.status == RuleStatus.FAIL.value]
    review = [r for r in rows if r.status == RuleStatus.REVIEW.value]
    top_severity = None
    if failed:
        top_severity = max(failed, key=lambda r: SEVERITY_ORDER.get(r.severity, 0)).severity

    return CaseListItem(
        case_id=case.case_id,
        created_at=case.created_at,
        status=case.status,
        classification=case.classification,
        overall_confidence=case.overall_confidence,
        product_name=case.product.name if case.product else None,
        brand=case.product.brand if case.product else None,
        identifier=case.product.identifier if case.product else None,
        top_severity=top_severity,
        failed_rules=len(failed),
        review_rules=len(review),
        is_golden=bool(case.is_golden),
    )
