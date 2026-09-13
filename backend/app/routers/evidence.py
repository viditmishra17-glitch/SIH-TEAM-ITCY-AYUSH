"""
Evidence endpoints — the feature that wins (Build Manual section 8).

Every finding points at an evidence id; this router turns that id into the
underlying source excerpt, the raw snapshot, or the actual pixels of the
physical label that produced the value.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CaseImage, Evidence, ListingSnapshot, OfficialRecord, Product
from app.core.database import get_db
from app.engine.rules import LISTING, OFFICIAL, PHOTO
from app.schemas.case import EvidenceRef
from app.pipeline.normalize import display_field
from app.pipeline.preprocess import crop_region

router = APIRouter(tags=["evidence"])


def _load(session: Session, case_id: str, evidence_id: str) -> Evidence:
    row = session.execute(
        select(Evidence).where(
            Evidence.case_id == case_id, Evidence.evidence_id == evidence_id
        )
    ).scalars().first()
    if row is None:
        raise HTTPException(
            status_code=404, detail=f"Evidence {evidence_id} not found on case {case_id}."
        )
    return row


@router.get("/cases/{case_id}/evidence/{evidence_id}", response_model=EvidenceRef)
def get_evidence(
    case_id: str, evidence_id: str, session: Session = Depends(get_db)
) -> EvidenceRef:
    """Serve the provenance behind one value: excerpt, snapshot and timestamps."""
    row = _load(session, case_id, evidence_id)

    metadata = dict(row.meta or {})

    # Attach the raw source payload so a judge can see the untouched response.
    if row.source_type in {LISTING, OFFICIAL}:
        product = session.execute(
            select(Product).where(Product.case_id == case_id)
        ).scalars().first()
        if product is not None:
            if row.source_type == LISTING:
                snapshot = session.execute(
                    select(ListingSnapshot).where(
                        ListingSnapshot.product_id == product.product_id
                    )
                ).scalars().first()
                if snapshot is not None:
                    metadata["raw_snapshot"] = snapshot.raw_json
            else:
                record = session.execute(
                    select(OfficialRecord).where(
                        OfficialRecord.product_id == product.product_id
                    )
                ).scalars().first()
                if record is not None:
                    metadata["raw_record"] = record.raw_json

    return EvidenceRef(
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
            f"/cases/{case_id}/evidence/{evidence_id}/crop"
            if row.bbox and row.source_type == PHOTO
            else None
        ),
        excerpt=row.excerpt,
        source_ref=row.source_ref,
        captured_at=row.captured_at,
        metadata=metadata,
    )


@router.get("/cases/{case_id}/evidence/{evidence_id}/crop")
def get_evidence_crop(
    case_id: str, evidence_id: str, session: Session = Depends(get_db)
) -> Response:
    """Cut the evidence crop out of the original image, on demand.

    Generated per request rather than written to disk: Render's filesystem is
    ephemeral, and the original bytes already live in the database.
    """
    row = _load(session, case_id, evidence_id)
    if row.source_type != PHOTO or not row.bbox:
        raise HTTPException(
            status_code=404,
            detail="This evidence has no image region (it came from a text source).",
        )

    image = session.execute(
        select(CaseImage).where(
            CaseImage.case_id == case_id, CaseImage.kind == "ORIGINAL"
        )
    ).scalars().first()
    if image is None:
        raise HTTPException(status_code=404, detail="Original image not found for this case.")

    try:
        crop = crop_region(image.data, row.bbox)
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=500, detail=f"Could not produce crop: {exc}") from exc

    return Response(
        content=crop,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )
