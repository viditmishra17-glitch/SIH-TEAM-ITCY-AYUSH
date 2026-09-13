"""
Evidence-backed case report.

The report is a *rendering* of the structured case result — never a second
decision engine (Build Manual section 20, step 10). It reads the same
``CaseResult`` the UI renders, so the two can never disagree.

HTML is generated with no template engine (one less dependency to break on
demo day). PDF uses reportlab when it is installed; when it is not, the route
degrades to HTML and says so rather than failing.
"""

from __future__ import annotations

import io
from datetime import datetime
from html import escape

from app.engine.classify import BOUNDARY_STATEMENT, describe
from app.schemas.case import CaseResult

_STATUS_MARK = {
    "PASS": "PASS",
    "FAIL": "FAIL",
    "REVIEW": "REVIEW",
    "NOT_APPLICABLE": "N/A",
    "MATCH": "MATCH",
    "MISMATCH": "MISMATCH",
    "INSUFFICIENT": "INSUFFICIENT",
}

_TONE_COLOUR = {
    "ok": "#1a7f4b",
    "bad": "#b3261e",
    "warn": "#8a5a00",
    "unknown": "#5a5f6a",
}


def _fmt_dt(value: datetime | None) -> str:
    if value is None:
        return "—"
    return value.strftime("%d %b %Y, %H:%M UTC")


def _fmt_conf(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.0f}%"


def render_html(result: CaseResult) -> str:
    """Self-contained HTML report. No external assets, prints cleanly."""
    info = describe(result.classification)
    colour = _TONE_COLOUR.get(info.tone, "#5a5f6a")

    material_badge = "<span class='mat'>material</span>"

    rows: list[str] = []
    for name in result.field_order:
        field = result.fields[name]
        badge = material_badge if field.is_material else ""
        rows.append(
            "<tr>"
            f"<td class='fname'>{escape(field.label)}{badge}</td>"
            f"<td>{escape(field.photo.display or '—')}</td>"
            f"<td>{escape(field.listing.display or '—')}</td>"
            f"<td>{escape(field.official.display or '—')}</td>"
            f"<td class='st st-{escape(field.status.lower())}'>"
            f"{escape(_STATUS_MARK.get(field.status, field.status))}</td>"
            "</tr>"
        )

    finding_rows: list[str] = []
    for finding in result.findings:
        if finding.status == "NOT_APPLICABLE":
            continue
        evidence = ", ".join(finding.evidence_ids) or "—"
        finding_rows.append(
            "<tr>"
            f"<td class='mono'>{escape(finding.rule_id)}</td>"
            f"<td class='st st-{escape(finding.status.lower())}'>{escape(finding.status)}</td>"
            f"<td>{escape(finding.severity)}</td>"
            f"<td>{escape(finding.explanation)}</td>"
            f"<td>{_fmt_conf(finding.confidence)}</td>"
            f"<td class='mono small'>{escape(evidence)}</td>"
            "</tr>"
        )

    source_rows: list[str] = []
    for key in ("PHOTO", "LISTING", "OFFICIAL"):
        source = result.sources.get(key)
        if source is None:
            continue
        status = "Available" if source.available else "Unavailable"
        detail = source.note or source.reference or source.source or "—"
        source_rows.append(
            "<tr>"
            f"<td>{escape(key.title())}</td>"
            f"<td>{escape(status)}</td>"
            f"<td>{escape(source.source or '—')}</td>"
            f"<td>{_fmt_dt(source.captured_at)}</td>"
            f"<td class='small'>{escape(detail)}</td>"
            "</tr>"
        )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>TriVerify case {escape(result.case_id)}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: 'Segoe UI', Helvetica, Arial, sans-serif; color:#1c2029;
         margin:0; padding:32px; background:#fff; font-size:13px; line-height:1.5; }}
  .wrap {{ max-width: 1000px; margin: 0 auto; }}
  header {{ border-bottom:3px solid {colour}; padding-bottom:16px; margin-bottom:22px; }}
  h1 {{ font-size:21px; margin:0 0 4px; letter-spacing:.4px; }}
  h2 {{ font-size:15px; margin:28px 0 10px; text-transform:uppercase;
        letter-spacing:.8px; color:#444a57; }}
  .sub {{ color:#5a5f6a; font-size:12px; }}
  .verdict {{ display:inline-block; padding:7px 14px; border-radius:4px; color:#fff;
              background:{colour}; font-weight:700; letter-spacing:.6px; font-size:14px; }}
  .headline {{ margin:14px 0 0; font-size:14px; }}
  .meta {{ display:flex; flex-wrap:wrap; gap:26px; margin-top:16px; }}
  .meta div span {{ display:block; font-size:11px; text-transform:uppercase;
                    letter-spacing:.6px; color:#6b7280; }}
  .meta div strong {{ font-size:15px; }}
  table {{ width:100%; border-collapse:collapse; margin-top:8px; }}
  th, td {{ text-align:left; padding:7px 9px; border-bottom:1px solid #e3e6ea;
            vertical-align:top; }}
  th {{ background:#f4f6f8; font-size:11px; text-transform:uppercase;
        letter-spacing:.6px; color:#4b5563; }}
  .fname {{ font-weight:600; white-space:nowrap; }}
  .mat {{ display:inline-block; margin-left:6px; font-size:9px; padding:1px 5px;
          border:1px solid #c3c8d0; border-radius:8px; color:#6b7280;
          text-transform:uppercase; letter-spacing:.4px; font-weight:600; }}
  .st {{ font-weight:700; font-size:11px; white-space:nowrap; }}
  .st-pass, .st-match {{ color:#1a7f4b; }}
  .st-fail, .st-mismatch {{ color:#b3261e; }}
  .st-review, .st-insufficient {{ color:#8a5a00; }}
  .st-not_applicable {{ color:#8b8f98; }}
  .mono {{ font-family: ui-monospace, 'Cascadia Mono', Consolas, monospace; }}
  .small {{ font-size:11px; color:#5a5f6a; }}
  footer {{ margin-top:30px; padding-top:14px; border-top:1px solid #e3e6ea;
            font-size:11px; color:#5a5f6a; }}
  @media print {{ body {{ padding:0; }} }}
</style></head><body><div class="wrap">
<header>
  <h1>TriVerify — Compliance Verification Report</h1>
  <div class="sub">Case {escape(result.case_id)} &middot; generated {_fmt_dt(datetime.utcnow())}
    &middot; rule set {escape(result.ruleset_version or '—')}</div>
  <div style="margin-top:14px"><span class="verdict">{escape(info.title.upper())}</span></div>
  <p class="headline">{escape(result.headline or info.trigger)}</p>
  <div class="meta">
    <div><span>Product</span><strong>{escape(result.product.name or '—')}</strong></div>
    <div><span>Brand</span><strong>{escape(result.product.brand or '—')}</strong></div>
    <div><span>Identifier</span><strong class="mono">{escape(result.product.identifier or '—')}</strong></div>
    <div><span>Confidence</span><strong>{_fmt_conf(result.overall_confidence)}</strong></div>
    <div><span>Verified</span><strong>{_fmt_dt(result.verified_at)}</strong></div>
  </div>
</header>

<h2>Source layers</h2>
<table><thead><tr><th>Layer</th><th>Status</th><th>Source</th><th>Captured</th><th>Detail</th></tr></thead>
<tbody>{''.join(source_rows)}</tbody></table>

<h2>Three-layer field comparison</h2>
<table><thead><tr><th>Declaration</th><th>Physical label</th><th>Seller listing</th>
<th>Official record</th><th>Status</th></tr></thead>
<tbody>{''.join(rows) or '<tr><td colspan="5">No comparable fields.</td></tr>'}</tbody></table>

<h2>Rule findings ({result.summary.failed} failed, {result.summary.review} for review,
{result.summary.passed} passed)</h2>
<table><thead><tr><th>Rule</th><th>Status</th><th>Severity</th><th>Explanation</th>
<th>Conf.</th><th>Evidence</th></tr></thead>
<tbody>{''.join(finding_rows) or '<tr><td colspan="6">No findings recorded.</td></tr>'}</tbody></table>

<footer><strong>Boundary statement.</strong> {escape(BOUNDARY_STATEMENT)}</footer>
</div></body></html>"""


def reportlab_available() -> bool:
    try:
        import reportlab  # noqa: F401
    except ImportError:
        return False
    return True


def render_pdf(result: CaseResult) -> bytes:
    """PDF rendering of the same structured result. Requires reportlab."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    info = describe(result.classification)
    accent = colors.HexColor(_TONE_COLOUR.get(info.tone, "#5a5f6a"))

    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "TVTitle", parent=styles["Title"], fontSize=16, alignment=TA_LEFT, spaceAfter=2
    )
    sub = ParagraphStyle("TVSub", parent=styles["Normal"], fontSize=8.5, textColor=colors.HexColor("#5a5f6a"))
    verdict = ParagraphStyle(
        "TVVerdict", parent=styles["Normal"], fontSize=13, textColor=accent, spaceBefore=10, leading=16
    )
    body = ParagraphStyle("TVBody", parent=styles["Normal"], fontSize=9, leading=12.5)
    cell = ParagraphStyle("TVCell", parent=styles["Normal"], fontSize=7.4, leading=9.6)
    heading = ParagraphStyle(
        "TVHead", parent=styles["Heading2"], fontSize=11, spaceBefore=14, spaceAfter=4
    )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title=f"TriVerify case {result.case_id}",
    )

    def table(data: list[list], widths: list[float]) -> Table:
        tbl = Table(data, colWidths=widths, repeatRows=1)
        tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f2f5")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#3d434f")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 7.4),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dfe3e8")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        return tbl

    story: list = [
        Paragraph("TriVerify — Compliance Verification Report", title),
        Paragraph(
            f"Case {escape(result.case_id)} &middot; generated {_fmt_dt(datetime.utcnow())} "
            f"&middot; rule set {escape(result.ruleset_version or '—')}",
            sub,
        ),
        Paragraph(f"<b>{escape(info.title.upper())}</b>", verdict),
        Paragraph(escape(result.headline or info.trigger), body),
        Spacer(1, 8),
    ]

    story.append(
        table(
            [
                ["Product", "Brand", "Identifier", "Confidence", "Verified"],
                [
                    Paragraph(escape(result.product.name or "—"), cell),
                    Paragraph(escape(result.product.brand or "—"), cell),
                    Paragraph(escape(result.product.identifier or "—"), cell),
                    _fmt_conf(result.overall_confidence),
                    _fmt_dt(result.verified_at),
                ],
            ],
            [46 * mm, 28 * mm, 34 * mm, 24 * mm, 46 * mm],
        )
    )

    story.append(Paragraph("Source layers", heading))
    source_data: list[list] = [["Layer", "Status", "Source", "Captured", "Detail"]]
    for key in ("PHOTO", "LISTING", "OFFICIAL"):
        source = result.sources.get(key)
        if source is None:
            continue
        source_data.append(
            [
                key.title(),
                "Available" if source.available else "Unavailable",
                Paragraph(escape(source.source or "—"), cell),
                _fmt_dt(source.captured_at),
                Paragraph(escape(source.note or source.reference or "—"), cell),
            ]
        )
    story.append(table(source_data, [20 * mm, 22 * mm, 38 * mm, 34 * mm, 64 * mm]))

    story.append(Paragraph("Three-layer field comparison", heading))
    field_data: list[list] = [
        ["Declaration", "Physical label", "Seller listing", "Official record", "Status"]
    ]
    for name in result.field_order:
        field = result.fields[name]
        field_data.append(
            [
                Paragraph(escape(field.label), cell),
                Paragraph(escape(field.photo.display or "—"), cell),
                Paragraph(escape(field.listing.display or "—"), cell),
                Paragraph(escape(field.official.display or "—"), cell),
                Paragraph(escape(_STATUS_MARK.get(field.status, field.status)), cell),
            ]
        )
    story.append(table(field_data, [34 * mm, 40 * mm, 40 * mm, 40 * mm, 24 * mm]))

    story.append(PageBreak())
    story.append(Paragraph("Rule findings", heading))
    finding_data: list[list] = [["Rule", "Status", "Sev.", "Explanation", "Conf.", "Evidence"]]
    for finding in result.findings:
        if finding.status == "NOT_APPLICABLE":
            continue
        finding_data.append(
            [
                Paragraph(escape(finding.rule_id), cell),
                Paragraph(escape(finding.status), cell),
                Paragraph(escape(finding.severity), cell),
                Paragraph(escape(finding.explanation), cell),
                _fmt_conf(finding.confidence),
                Paragraph(escape(", ".join(finding.evidence_ids) or "—"), cell),
            ]
        )
    story.append(
        table(finding_data, [17 * mm, 16 * mm, 14 * mm, 80 * mm, 13 * mm, 38 * mm])
    )

    story.append(Spacer(1, 12))
    story.append(Paragraph(f"<b>Boundary statement.</b> {escape(BOUNDARY_STATEMENT)}", cell))

    doc.build(story)
    return buffer.getvalue()
