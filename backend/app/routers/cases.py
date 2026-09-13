"""Case endpoints — create, read, verify, list, images."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core import config
from app.services.presenter import build_case_result, build_list_item
from app.services.case_service import CaseNotFound, create_case, get_case, verify_case
from app.models import Case, CaseImage, Product
from app.core.database import get_db
from app.schemas.case import (
    CaseCreateResponse,
    CaseListResponse,
    CaseResult,
)
from app.pipeline.preprocess import ImageDecodeError

router = APIRouter(tags=["cases"])

_ALLOWED_IMAGE_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
    "image/bmp",
    "image/tiff",
}


@router.post("/cases", response_model=CaseCreateResponse, status_code=201)
async def create_verification_case(
    image: UploadFile = File(..., description="Photograph of the packaged commodity"),
    identifier: str = Form(..., description="Product identifier (EAN/barcode/SKU)"),
    product_name: str | None = Form(None),
    brand: str | None = Form(None),
    category: str | None = Form(None),
    session: Session = Depends(get_db),
) -> CaseCreateResponse:
    """Create a verification case from an uploaded image + product identifier."""
    identifier = (identifier or "").strip()
    if not identifier:
        raise HTTPException(status_code=422, detail="A product identifier is required.")

    if image.content_type and image.content_type.lower() not in _ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported image type {image.content_type!r}. Use PNG, JPEG, WEBP, BMP or TIFF.",
        )

    data = await image.read()
    if not data:
        raise HTTPException(status_code=422, detail="The uploaded file is empty.")
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Image exceeds the {config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.",
        )

    try:
        case = create_case(
            session,
            image_bytes=data,
            filename=image.filename,
            identifier=identifier,
            product_hints={
                "name": (product_name or "").strip() or None,
                "brand": (brand or "").strip() or None,
                "category": (category or "").strip() or None,
            },
        )
    except ImageDecodeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return CaseCreateResponse(
        case_id=case.case_id,
        status=case.status,
        classification=case.classification,
        message=case.headline or "Case created.",
    )


@router.get("/cases", response_model=CaseListResponse)
def list_cases(
    q: str | None = Query(None, description="Search case id, product, brand or identifier"),
    classification: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_db),
) -> CaseListResponse:
    """Minimal inspection history / search."""
    stmt = select(Case).outerjoin(Product, Product.case_id == Case.case_id)

    if q:
        pattern = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                Case.case_id.ilike(pattern),
                Product.name.ilike(pattern),
                Product.brand.ilike(pattern),
                Product.identifier.ilike(pattern),
            )
        )
    if classification:
        stmt = stmt.where(Case.classification == classification.strip().upper())

    all_matching = session.execute(stmt.order_by(Case.case_id.desc())).scalars().unique().all()
    page = all_matching[offset : offset + limit]

    return CaseListResponse(
        total=len(all_matching),
        items=[build_list_item(session, case) for case in page],
    )


@router.get("/cases/{case_id}", response_model=CaseResult)
def get_case_result(case_id: str, session: Session = Depends(get_db)) -> CaseResult:
    """Complete verification result: comparisons, findings, evidence, confidence."""
    try:
        case = get_case(session, case_id)
    except CaseNotFound:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found.") from None
    return build_case_result(session, case)


@router.post("/cases/{case_id}/verify", response_model=CaseResult)
def reverify_case(case_id: str, session: Session = Depends(get_db)) -> CaseResult:
    """Run or re-run deterministic verification against the stored evidence."""
    try:
        case = get_case(session, case_id)
    except CaseNotFound:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found.") from None

    verify_case(session, case)
    session.refresh(case)
    return build_case_result(session, case)


@router.get("/cases/{case_id}/images/{image_id}")
def get_case_image(
    case_id: str, image_id: str, session: Session = Depends(get_db)
) -> Response:
    """Serve a stored image. Bytes come from the database, not the filesystem."""
    image = session.execute(
        select(CaseImage).where(
            CaseImage.case_id == case_id, CaseImage.image_id == image_id
        )
    ).scalars().first()
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found.")
    return Response(
        content=image.data,
        media_type=image.content_type or "image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )
