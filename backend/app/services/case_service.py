"""
Case orchestration: ingest → extract → acquire sources → reconcile → persist.

This is the only module that knows about both the pipeline and the database.
The routers stay thin, and the engine stays pure.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import config
from app.models import (
    Case,
    CaseImage,
    Evidence,
    ImageObservation,
    ListingField,
    ListingSnapshot,
    OfficialField,
    OfficialRecord,
    Product,
    RuleResult,
    utcnow,
)
from app.engine.reconcile import FieldValue, LayerData, VerificationOutcome, reconcile
from app.engine.rules import LISTING, OFFICIAL, PHOTO
from app.engine.vocabulary import CANONICAL_FIELDS, CaseStatus
from app.pipeline.adapters import SourceUnavailable, get_ecommerce_adapter, get_official_adapter
from app.pipeline.adapters.base import Snapshot
from app.pipeline.extract import ExtractionResult, extract_from_image
from app.pipeline.normalize import display_field

_CASE_ID_RE = re.compile(r"^TV-(\d+)$")


class CaseNotFound(LookupError):
    pass


# ---------------------------------------------------------------------------
# Identifier allocation
# ---------------------------------------------------------------------------


def next_case_id(session: Session) -> str:
    """Allocate the next TV-#### id.

    Collisions are still possible under concurrency, so the caller retries —
    see :func:`create_case`.
    """
    highest = 0
    for (case_id,) in session.execute(select(Case.case_id)):
        match = _CASE_ID_RE.match(case_id or "")
        if match:
            highest = max(highest, int(match.group(1)))
    return f"TV-{highest + 1:04d}"


def _case_number(case_id: str) -> str:
    match = _CASE_ID_RE.match(case_id)
    return match.group(1) if match else re.sub(r"[^0-9A-Za-z]", "", case_id)[:6] or "0000"


class _EvidenceIds:
    """Deterministic evidence ids, so seeded cases are byte-stable."""

    def __init__(self, case_id: str) -> None:
        self._prefix = f"EV-{_case_number(case_id)}"
        self._n = 0

    def next(self) -> str:
        self._n += 1
        return f"{self._prefix}-{self._n:02d}"


# ---------------------------------------------------------------------------
# Source acquisition
# ---------------------------------------------------------------------------


def _fetch_snapshot(kind: str, identifier: str, hints: dict | None) -> tuple[Snapshot | None, str | None]:
    adapter = get_ecommerce_adapter() if kind == LISTING else get_official_adapter()
    try:
        return adapter.fetch(identifier, hints), None
    except SourceUnavailable as exc:
        return None, str(exc)
    except Exception as exc:  # never let an adapter crash a demo
        return None, f"Source adapter error: {exc}"


# ---------------------------------------------------------------------------
# Case creation
# ---------------------------------------------------------------------------


def create_case(
    session: Session,
    *,
    image_bytes: bytes,
    filename: str | None,
    identifier: str,
    product_hints: dict[str, Any] | None = None,
    case_id: str | None = None,
    is_golden: bool = False,
) -> Case:
    """Full ingestion path. Commits and returns the verified case."""
    hints = dict(product_hints or {})
    identifier = str(identifier).strip()

    extraction = extract_from_image(image_bytes)

    attempts = 0
    while True:
        attempts += 1
        allocated = case_id or next_case_id(session)
        case = Case(
            case_id=allocated,
            created_at=utcnow(),
            status=CaseStatus.EXTRACTED.value,
            is_golden=is_golden,
            ruleset_version=config.RULESET_VERSION,
            extraction_notes=list(extraction.notes),
        )
        session.add(case)
        try:
            session.flush()
            break
        except IntegrityError:
            session.rollback()
            if case_id is not None or attempts >= 5:
                raise
            continue

    product = Product(
        product_id=f"P-{_case_number(case.case_id)}",
        case_id=case.case_id,
        name=hints.get("name"),
        brand=hints.get("brand"),
        category=hints.get("category"),
        identifier=identifier or None,
    )
    session.add(product)

    _store_images(session, case, extraction, filename)
    _store_observations(session, product, extraction, filename)

    source_notes: dict[str, str] = {}

    listing_snapshot, listing_error = _fetch_snapshot(LISTING, identifier, hints)
    if listing_snapshot is not None:
        _store_listing(session, product, case.case_id, listing_snapshot)
    elif listing_error:
        source_notes[LISTING] = listing_error

    official_snapshot, official_error = _fetch_snapshot(OFFICIAL, identifier, hints)
    if official_snapshot is not None:
        _store_official(session, product, case.case_id, official_snapshot)
    elif official_error:
        source_notes[OFFICIAL] = official_error

    if not extraction.available:
        source_notes[PHOTO] = extraction.ocr.unavailable_reason or "OCR unavailable."

    # Backfill product identity from whatever source knows it.
    _enrich_product(product, extraction, listing_snapshot, official_snapshot, identifier)

    case.source_notes = source_notes
    session.flush()

    verify_case(session, case, commit=False)
    session.commit()
    session.refresh(case)
    return case


def _store_images(
    session: Session, case: Case, extraction: ExtractionResult, filename: str | None
) -> None:
    pre = extraction.preprocess
    number = _case_number(case.case_id)
    session.add(
        CaseImage(
            image_id=f"IMG-{number}-O",
            case_id=case.case_id,
            kind="ORIGINAL",
            filename=filename,
            content_type="image/png",
            width=pre.original_size[0],
            height=pre.original_size[1],
            quality_score=pre.quality_score,
            data=pre.original_bytes,
        )
    )
    session.add(
        CaseImage(
            image_id=f"IMG-{number}-P",
            case_id=case.case_id,
            kind="PREPROCESSED",
            filename=filename,
            content_type="image/png",
            width=pre.processed_size[0],
            height=pre.processed_size[1],
            quality_score=pre.quality_score,
            data=pre.processed_bytes,
        )
    )


def _store_observations(
    session: Session, product: Product, extraction: ExtractionResult, filename: str | None
) -> None:
    for index, obs in enumerate(extraction.observations, start=1):
        session.add(
            ImageObservation(
                obs_id=f"OBS-{product.product_id[2:]}-{index:03d}",
                product_id=product.product_id,
                image_path=filename,
                field_name=obs.field_name,
                value_raw=obs.value_raw,
                value_norm=obs.value_norm,
                bbox=obs.bbox,
                confidence=obs.confidence,
                engine=obs.engine,
            )
        )


def _store_listing(
    session: Session, product: Product, case_id: str, snapshot: Snapshot
) -> None:
    snapshot_id = f"LS-{_case_number(case_id)}"
    session.add(
        ListingSnapshot(
            snapshot_id=snapshot_id,
            product_id=product.product_id,
            source=snapshot.source,
            url_or_id=snapshot.url_or_id,
            captured_at=snapshot.captured_at,
            is_live=snapshot.is_live,
            raw_json=snapshot.raw_json,
        )
    )
    normalized = snapshot.normalized_fields()
    for name, raw in snapshot.fields.items():
        if name not in CANONICAL_FIELDS:
            continue
        session.add(
            ListingField(
                snapshot_id=snapshot_id,
                field_name=name,
                value_raw=raw,
                value_norm=normalized.get(name),
                confidence=1.0,
            )
        )


def _store_official(
    session: Session, product: Product, case_id: str, snapshot: Snapshot
) -> None:
    record_id = f"OR-{_case_number(case_id)}"
    session.add(
        OfficialRecord(
            record_id=record_id,
            product_id=product.product_id,
            source=snapshot.source,
            url_or_id=snapshot.url_or_id,
            captured_at=snapshot.captured_at,
            is_live=snapshot.is_live,
            raw_json=snapshot.raw_json,
        )
    )
    normalized = snapshot.normalized_fields()
    for name, raw in snapshot.fields.items():
        if name not in CANONICAL_FIELDS:
            continue
        session.add(
            OfficialField(
                record_id=record_id,
                field_name=name,
                value_raw=raw,
                value_norm=normalized.get(name),
            )
        )


def _enrich_product(
    product: Product,
    extraction: ExtractionResult,
    listing: Snapshot | None,
    official: Snapshot | None,
    identifier: str,
) -> None:
    observed = extraction.by_field()

    def pick(field: str) -> str | None:
        if listing and listing.fields.get(field):
            return listing.fields[field]
        if official and official.fields.get(field):
            return official.fields[field]
        obs = observed.get(field)
        return obs.value_raw if obs else None

    product.name = product.name or pick("product_name")
    product.brand = product.brand or pick("brand")
    product.identifier = product.identifier or identifier or pick("identifier")


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def _load_layers(session: Session, case: Case) -> tuple[dict[str, LayerData], list[Evidence]]:
    """Rebuild the three layers from persisted data and mint evidence rows."""
    notes: dict[str, str] = dict(case.source_notes or {})
    ids = _EvidenceIds(case.case_id)
    evidence: list[Evidence] = []

    product = case.product
    layers: dict[str, LayerData] = {}

    # ---- PHOTO -----------------------------------------------------------
    observations = (
        session.execute(
            select(ImageObservation)
            .where(ImageObservation.product_id == (product.product_id if product else ""))
            .order_by(ImageObservation.obs_id)
        )
        .scalars()
        .all()
        if product
        else []
    )

    best: dict[str, ImageObservation] = {}
    for obs in observations:
        current = best.get(obs.field_name)
        if current is None:
            best[obs.field_name] = obs
            continue
        if (obs.value_norm is not None, obs.confidence) > (
            current.value_norm is not None,
            current.confidence,
        ):
            best[obs.field_name] = obs

    photo_available = PHOTO not in notes
    photo_fields: dict[str, FieldValue] = {}
    if photo_available:
        for name in CANONICAL_FIELDS:
            obs = best.get(name)
            if obs is None:
                continue
            evidence_id = ids.next()
            photo_fields[name] = FieldValue(
                raw=obs.value_raw,
                norm=obs.value_norm,
                confidence=float(obs.confidence or 0.0),
                evidence_id=evidence_id,
                bbox=obs.bbox,
            )
            evidence.append(
                Evidence(
                    evidence_id=evidence_id,
                    case_id=case.case_id,
                    source_type=PHOTO,
                    source_ref=obs.image_path or "uploaded image",
                    field_name=name,
                    raw_value=obs.value_raw,
                    normalized_value=obs.value_norm,
                    bbox=obs.bbox,
                    excerpt=obs.value_raw,
                    confidence=float(obs.confidence or 0.0),
                    captured_at=case.created_at or utcnow(),
                    meta={"engine": obs.engine, "obs_id": obs.obs_id},
                )
            )

    layers[PHOTO] = LayerData(
        layer=PHOTO,
        available=photo_available,
        reason=notes.get(PHOTO),
        source="uploaded product photograph",
        reference=None,
        captured_at=case.created_at,
        fields=photo_fields,
    )

    # ---- LISTING ---------------------------------------------------------
    snapshot = (
        session.execute(
            select(ListingSnapshot).where(
                ListingSnapshot.product_id == (product.product_id if product else "")
            )
        )
        .scalars()
        .first()
        if product
        else None
    )
    listing_fields: dict[str, FieldValue] = {}
    if snapshot is not None:
        rows = (
            session.execute(
                select(ListingField)
                .where(ListingField.snapshot_id == snapshot.snapshot_id)
                .order_by(ListingField.id)
            )
            .scalars()
            .all()
        )
        for row in rows:
            evidence_id = ids.next()
            listing_fields[row.field_name] = FieldValue(
                raw=row.value_raw,
                norm=row.value_norm,
                confidence=float(row.confidence or 1.0),
                evidence_id=evidence_id,
            )
            evidence.append(
                Evidence(
                    evidence_id=evidence_id,
                    case_id=case.case_id,
                    source_type=LISTING,
                    source_ref=snapshot.url_or_id or snapshot.source,
                    field_name=row.field_name,
                    raw_value=row.value_raw,
                    normalized_value=row.value_norm,
                    excerpt=f"{row.field_name}: {row.value_raw}",
                    confidence=float(row.confidence or 1.0),
                    captured_at=snapshot.captured_at,
                    meta={
                        "snapshot_id": snapshot.snapshot_id,
                        "source": snapshot.source,
                        "is_live": snapshot.is_live,
                    },
                )
            )

    layers[LISTING] = LayerData(
        layer=LISTING,
        available=snapshot is not None,
        reason=notes.get(LISTING),
        source=snapshot.source if snapshot else None,
        reference=snapshot.url_or_id if snapshot else None,
        captured_at=snapshot.captured_at if snapshot else None,
        is_live=bool(snapshot.is_live) if snapshot else False,
        fields=listing_fields,
    )

    # ---- OFFICIAL --------------------------------------------------------
    record = (
        session.execute(
            select(OfficialRecord).where(
                OfficialRecord.product_id == (product.product_id if product else "")
            )
        )
        .scalars()
        .first()
        if product
        else None
    )
    official_fields: dict[str, FieldValue] = {}
    if record is not None:
        rows = (
            session.execute(
                select(OfficialField)
                .where(OfficialField.record_id == record.record_id)
                .order_by(OfficialField.id)
            )
            .scalars()
            .all()
        )
        for row in rows:
            evidence_id = ids.next()
            official_fields[row.field_name] = FieldValue(
                raw=row.value_raw,
                norm=row.value_norm,
                confidence=1.0,
                evidence_id=evidence_id,
            )
            evidence.append(
                Evidence(
                    evidence_id=evidence_id,
                    case_id=case.case_id,
                    source_type=OFFICIAL,
                    source_ref=record.url_or_id or record.source,
                    field_name=row.field_name,
                    raw_value=row.value_raw,
                    normalized_value=row.value_norm,
                    excerpt=f"{row.field_name}: {row.value_raw}",
                    confidence=1.0,
                    captured_at=record.captured_at,
                    meta={
                        "record_id": record.record_id,
                        "source": record.source,
                        "is_live": record.is_live,
                    },
                )
            )

    layers[OFFICIAL] = LayerData(
        layer=OFFICIAL,
        available=record is not None,
        reason=notes.get(OFFICIAL),
        source=record.source if record else None,
        reference=record.url_or_id if record else None,
        captured_at=record.captured_at if record else None,
        is_live=bool(record.is_live) if record else False,
        fields=official_fields,
    )

    return layers, evidence


def verify_case(session: Session, case: Case, commit: bool = True) -> VerificationOutcome:
    """Run (or re-run) deterministic verification for a case."""
    layers, evidence = _load_layers(session, case)

    # Replace prior evidence and results so a re-run is idempotent.
    for existing in list(case.evidence):
        session.delete(existing)
    for existing in list(case.rule_results):
        session.delete(existing)
    session.flush()

    for row in evidence:
        session.add(row)

    outcome = reconcile(layers)

    number = _case_number(case.case_id)
    for index, finding in enumerate(outcome.findings, start=1):
        session.add(
            RuleResult(
                result_id=f"RR-{number}-{index:03d}",
                case_id=case.case_id,
                rule_id=finding.rule_id,
                field_name=finding.field_name,
                status=finding.status,
                severity=finding.severity,
                explanation=finding.explanation,
                confidence=finding.confidence,
                evidence_refs=finding.evidence_ids,
                ordinal=index,
            )
        )

    case.classification = outcome.classification
    case.overall_confidence = outcome.overall_confidence
    case.headline = outcome.headline
    case.status = CaseStatus.VERIFIED.value
    case.verified_at = datetime.now(timezone.utc)
    case.ruleset_version = outcome.ruleset_version

    session.flush()
    if commit:
        session.commit()
    return outcome


def get_case(session: Session, case_id: str) -> Case:
    case = session.get(Case, case_id)
    if case is None:
        raise CaseNotFound(case_id)
    return case


def field_display(field_name: str, norm: Any, raw: str | None) -> str | None:
    return display_field(field_name, norm if isinstance(norm, dict) else None) or raw


def count_cases(session: Session, golden_only: bool = False) -> int:
    stmt = select(func.count()).select_from(Case)
    if golden_only:
        stmt = stmt.where(Case.is_golden.is_(True))
    return int(session.execute(stmt).scalar_one())
