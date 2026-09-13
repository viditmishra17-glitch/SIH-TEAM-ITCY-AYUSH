"""
M2b — Declaration extraction (Build Manual section 6).

JOB:       pull the legally relevant declarations out of OCR lines.
INPUT:     preprocessed image.
OUTPUT:    field / raw value / normalized value / bbox / confidence tuples.
DONE WHEN: the evidence panel can jump from a field to the image region that
           produced it.
CONSTRAINT: low-confidence fields become REVIEW, never silently accepted.

Approach: label-anchored parsing, no LLM. For each OCR line we find every
label that appears in it, then take each label's value as the text running up
to the next label on that line. This handles the very common
``MFG: DEC 2025   EXP: DEC 2026`` single-line case correctly instead of
letting the first label swallow the whole line.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field

from app.engine import vocabulary as V
from app.pipeline.normalize import clean_text, normalize_field
from app.pipeline.ocr import OcrLine, OcrResult, run_ocr
from app.pipeline.preprocess import PreprocessResult, preprocess_image

# ---------------------------------------------------------------------------
# Label patterns
# ---------------------------------------------------------------------------

# Order matters only for readability; matching is positional, not sequential.
# Longer/more specific alternatives are listed first inside each pattern so
# "Best Before" is never matched as "Before".
_LABEL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        V.MRP,
        re.compile(
            r"\b(?:maximum\s+retail\s+price|m\.?\s?r\.?\s?p\.?|mrp)\b[\s:.\-]*",
            re.IGNORECASE,
        ),
    ),
    (
        V.NET_QUANTITY,
        re.compile(
            r"\b(?:net\s+(?:quantity|qty|weight|wt|content[s]?|vol(?:ume)?)|net\s?wt)\b[\s:.\-]*",
            re.IGNORECASE,
        ),
    ),
    (
        V.EXPIRY_DATE,
        re.compile(
            r"\b(?:best\s+before|use\s+by|expiry\s+date|expires\s+on|exp\.?\s?dt|exp)\b[\s:.\-]*",
            re.IGNORECASE,
        ),
    ),
    (
        V.MANUFACTURING_DATE,
        re.compile(
            r"\b(?:date\s+of\s+manufacture|manufacturing\s+date|manufactured\s+on|mfg\.?\s?dt|mfg|mfd)\b[\s:.\-]*",
            re.IGNORECASE,
        ),
    ),
    (
        V.PACKING_DATE,
        re.compile(
            r"\b(?:date\s+of\s+pack(?:ing|ed)?|packed\s+on|pkd\.?\s?dt|pkd)\b[\s:.\-]*",
            re.IGNORECASE,
        ),
    ),
    (
        V.MANUFACTURER_NAME,
        re.compile(
            r"\b(?:manufactured\s+(?:&|and)\s+marketed\s+by|manufactured\s+by|mfd\.?\s+by|mfg\.?\s+by|manufacturer)\b[\s:.\-]*",
            re.IGNORECASE,
        ),
    ),
    (
        V.PACKER_NAME,
        re.compile(r"\b(?:packed\s+(?:&|and)\s+marketed\s+by|packed\s+by|packer)\b[\s:.\-]*", re.IGNORECASE),
    ),
    (
        V.IMPORTER_NAME,
        re.compile(r"\b(?:imported\s+(?:&|and)\s+marketed\s+by|imported\s+by|importer)\b[\s:.\-]*", re.IGNORECASE),
    ),
    (
        V.CONSUMER_CARE,
        re.compile(
            r"\b(?:consumer\s+care|customer\s+care|consumer\s+complaints?|helpline|care\s+no|toll\s+free)\b[\s:.\-]*",
            re.IGNORECASE,
        ),
    ),
    (
        V.IDENTIFIER,
        re.compile(r"\b(?:batch\s+no|batch|lot\s+no|lot|ean|gtin|barcode|sku)\b[\s:.\-]*", re.IGNORECASE),
    ),
    (V.BRAND, re.compile(r"\b(?:brand)\b[\s:.\-]*", re.IGNORECASE)),
    (V.PRODUCT_NAME, re.compile(r"\b(?:product\s+name|product)\b[\s:.\-]*", re.IGNORECASE)),
]

#: A bare quantity on its own line ("500 g") with no label at all.
_BARE_QUANTITY_RE = re.compile(
    r"^\s*\d+(?:[.,]\d+)?\s*(?:mg|g|gm|gms|kg|ml|l|ltr|litre|liter|n|nos|pcs|pieces|units?)\.?\s*$",
    re.IGNORECASE,
)

#: A bare price on its own line.
_BARE_PRICE_RE = re.compile(r"^\s*(?:₹|rs\.?|inr)\s*\d", re.IGNORECASE)

#: 8–14 digit product code sitting alone.
_BARE_CODE_RE = re.compile(r"^\s*\d{8,14}\s*$")


@dataclass
class Observation:
    """One extracted declaration with its visual provenance."""

    field_name: str
    value_raw: str
    value_norm: dict | None
    bbox: list[float]
    confidence: float
    line_index: int
    engine: str


@dataclass
class ExtractionResult:
    preprocess: PreprocessResult
    ocr: OcrResult
    observations: list[Observation] = dc_field(default_factory=list)
    #: Every OCR line, in original-image coordinates, for the evidence overlay.
    lines: list[OcrLine] = dc_field(default_factory=list)
    notes: list[str] = dc_field(default_factory=list)

    @property
    def available(self) -> bool:
        return self.ocr.available

    def by_field(self) -> dict[str, Observation]:
        """Best observation per field — highest confidence wins, ties by order."""
        best: dict[str, Observation] = {}
        for obs in self.observations:
            current = best.get(obs.field_name)
            if current is None:
                best[obs.field_name] = obs
                continue
            # Prefer a value that actually normalized, then higher confidence.
            current_ok = current.value_norm is not None
            new_ok = obs.value_norm is not None
            if (new_ok, obs.confidence) > (current_ok, current.confidence):
                best[obs.field_name] = obs
        return best


def _rescale(bbox: list[float], factor: float) -> list[float]:
    if factor == 1.0:
        return [float(v) for v in bbox]
    return [round(float(v) / factor, 2) for v in bbox]


def _find_labels(text: str) -> list[tuple[int, int, str]]:
    """Return (start, end, field_name) for every label occurrence in a line."""
    hits: list[tuple[int, int, str]] = []
    for field_name, pattern in _LABEL_PATTERNS:
        for match in pattern.finditer(text):
            hits.append((match.start(), match.end(), field_name))
    if not hits:
        return []

    # Drop labels contained inside an earlier, longer label match
    # (e.g. "mfg" inside "manufactured by", "exp" inside "expiry date").
    hits.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    kept: list[tuple[int, int, str]] = []
    for start, end, field_name in hits:
        if any(start < k_end and end > k_start for k_start, k_end, _ in kept):
            continue
        kept.append((start, end, field_name))
    kept.sort(key=lambda item: item[0])
    return kept


def _split_line(text: str) -> list[tuple[str, str]]:
    """Split a line into (field_name, value) pairs using label anchors."""
    labels = _find_labels(text)
    if not labels:
        return []
    results: list[tuple[str, str]] = []
    for index, (_, end, field_name) in enumerate(labels):
        stop = labels[index + 1][0] if index + 1 < len(labels) else len(text)
        value = clean_text(text[end:stop]).strip(" :.-|,")
        if value:
            results.append((field_name, value))
    return results


def extract_observations(
    lines: list[OcrLine], engine: str
) -> tuple[list[Observation], list[str]]:
    """Turn OCR lines into field observations. Pure function — easy to test."""
    observations: list[Observation] = []
    notes: list[str] = []
    labelled_line_indices: set[int] = set()

    for index, line in enumerate(lines):
        text = clean_text(line.text)
        if not text:
            continue

        pairs = _split_line(text)
        if pairs:
            labelled_line_indices.add(index)
        for field_name, value in pairs:
            observations.append(
                Observation(
                    field_name=field_name,
                    value_raw=value,
                    value_norm=normalize_field(field_name, value),
                    bbox=list(line.bbox),
                    confidence=round(float(line.confidence), 4),
                    line_index=index,
                    engine=engine,
                )
            )

    # Unlabelled lines: a few shapes are unambiguous on their own.
    for index, line in enumerate(lines):
        if index in labelled_line_indices:
            continue
        text = clean_text(line.text)
        if not text:
            continue
        bare_field: str | None = None
        if _BARE_PRICE_RE.match(text):
            bare_field = V.MRP
        elif _BARE_QUANTITY_RE.match(text):
            bare_field = V.NET_QUANTITY
        elif _BARE_CODE_RE.match(text):
            bare_field = V.IDENTIFIER
        if bare_field is None:
            continue
        observations.append(
            Observation(
                field_name=bare_field,
                value_raw=text,
                value_norm=normalize_field(bare_field, text),
                bbox=list(line.bbox),
                # Unlabelled inference is weaker evidence than a labelled one.
                confidence=round(float(line.confidence) * 0.9, 4),
                line_index=index,
                engine=engine,
            )
        )

    # Product name: the first substantial unlabelled line, if nothing explicit.
    if not any(obs.field_name == V.PRODUCT_NAME for obs in observations):
        for index, line in enumerate(lines):
            if index in labelled_line_indices:
                continue
            text = clean_text(line.text)
            letters = sum(ch.isalpha() for ch in text)
            if letters >= 4 and not _BARE_QUANTITY_RE.match(text):
                observations.append(
                    Observation(
                        field_name=V.PRODUCT_NAME,
                        value_raw=text,
                        value_norm=normalize_field(V.PRODUCT_NAME, text),
                        bbox=list(line.bbox),
                        confidence=round(float(line.confidence) * 0.9, 4),
                        line_index=index,
                        engine=engine,
                    )
                )
                break

    for obs in observations:
        if obs.value_norm is None:
            notes.append(
                f"Could not normalize {V.FIELD_LABELS.get(obs.field_name, obs.field_name)} "
                f"value {obs.value_raw!r} — routed to review."
            )

    return observations, notes


def extract_from_image(image_bytes: bytes) -> ExtractionResult:
    """Full M1+M2 path: bytes in, observations with provenance out.

    All bounding boxes come back in ORIGINAL image coordinates, so evidence
    crops are cut from the untouched photo the officer uploaded.
    """
    pre = preprocess_image(image_bytes)
    ocr = run_ocr(pre.original_bytes, pre.processed_bytes)

    if not ocr.available:
        return ExtractionResult(
            preprocess=pre,
            ocr=ocr,
            observations=[],
            lines=[],
            notes=[ocr.unavailable_reason or "OCR unavailable."],
        )

    factor = pre.scale if ocr.coordinate_space == "processed" else 1.0
    lines = [
        OcrLine(text=line.text, bbox=_rescale(line.bbox, factor), confidence=line.confidence)
        for line in ocr.lines
    ]

    observations, notes = extract_observations(lines, ocr.engine)
    if pre.quality_score < 0.35:
        notes.append(
            f"Image quality score is low ({pre.quality_score:.2f}); "
            "extraction confidence should be treated with caution."
        )
    return ExtractionResult(
        preprocess=pre, ocr=ocr, observations=observations, lines=lines, notes=notes
    )
