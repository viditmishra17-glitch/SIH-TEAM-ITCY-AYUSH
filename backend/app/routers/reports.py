"""Report endpoints — generate and serve the evidence-backed case report."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.core import config
from app.services.presenter import build_case_result
from app.services.report_builder import render_html, render_pdf, reportlab_available
from app.services.case_service import CaseNotFound, get_case
from app.models import Report, utcnow
from app.core.database import get_db
from app.schemas.case import CaseResult

router = APIRouter(tags=["reports"])


@router.get("/cases/{case_id}/report")
def get_report(
    case_id: str,
    format: str = Query("html", pattern="^(html|pdf|json)$"),
    session: Session = Depends(get_db),
):
    """Generate (and record) the case report.

    ``html`` always works. ``pdf`` requires reportlab; if it is missing the
    route says so explicitly instead of returning a broken file — the manual's
    fallback for a broken report generator is to serve the stable rendering.
    """
    try:
        case = get_case(session, case_id)
    except CaseNotFound:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found.") from None

    result: CaseResult = build_case_result(session, case)

    if format == "json":
        return result

    if format == "pdf":
        if not reportlab_available():
            raise HTTPException(
                status_code=503,
                detail=(
                    "PDF export is unavailable because reportlab is not installed. "
                    f"Use /cases/{case_id}/report?format=html instead, or "
                    "pip install reportlab."
                ),
            )
        try:
            pdf = render_pdf(result)
        except Exception as exc:  # keep the demo alive; HTML still works
            raise HTTPException(
                status_code=503,
                detail=(
                    f"PDF generation failed ({exc}). "
                    f"Use /cases/{case_id}/report?format=html instead."
                ),
            ) from exc

        _record(session, case_id, "pdf", None)
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="triverify-{case_id}.pdf"'
            },
        )

    html = render_html(result)
    _record(session, case_id, "html", html)
    return HTMLResponse(content=html)


def _record(session: Session, case_id: str, fmt: str, content: str | None) -> None:
    """Keep a row per generated report so the case has an audit trail."""
    report_id = f"RP-{case_id.split('-')[-1]}-{fmt.upper()}"
    existing = session.get(Report, report_id)
    file_path = str(config.REPORTS_DIR / f"triverify-{case_id}.{fmt}")
    if existing is None:
        session.add(
            Report(
                report_id=report_id,
                case_id=case_id,
                generated_at=utcnow(),
                fmt=fmt,
                file_path=file_path,
                content=content,
            )
        )
    else:
        existing.generated_at = utcnow()
        existing.content = content
        existing.file_path = file_path
    session.commit()
