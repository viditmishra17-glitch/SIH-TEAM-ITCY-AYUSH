"""
M2a — OCR (Build Manual section 6).

Two interchangeable engines behind one interface, because the manual's
fallback matrix says poor OCR must degrade to a precomputed fixture rather
than break the demo:

``FixtureOcrEngine``    reads committed OCR output keyed by image content
                       hash. Deterministic, offline, and what the golden
                       cases and CI run against.
``TesseractOcrEngine``  real OCR, used automatically for images that have no
                       fixture, when pytesseract and the binary are present.

Both return the same thing: a list of ``OcrLine``. The field extractor never
knows which engine ran, so extraction logic is tested identically either way.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from app.core import config


@dataclass(frozen=True)
class OcrLine:
    """One line of recognized text with its region on the processed image."""

    text: str
    bbox: list[float]  # [x, y, w, h]
    confidence: float

    def to_dict(self) -> dict:
        return {"text": self.text, "bbox": list(self.bbox), "confidence": self.confidence}


@dataclass
class OcrResult:
    engine: str
    lines: list[OcrLine] = field(default_factory=list)
    #: Set when no engine could run. The case must go to REVIEW, not PASS.
    unavailable_reason: str | None = None
    #: Which image the bboxes refer to: "original" or "processed".
    #: The extractor rescales everything to original-image coordinates so that
    #: evidence crops are always cut from the untouched photo.
    coordinate_space: str = "original"

    @property
    def available(self) -> bool:
        return self.unavailable_reason is None

    @property
    def mean_confidence(self) -> float:
        if not self.lines:
            return 0.0
        return round(sum(line.confidence for line in self.lines) / len(self.lines), 4)


class OcrEngine(Protocol):
    name: str

    def available(self) -> bool: ...

    def run(self, image_bytes: bytes) -> OcrResult: ...


def file_key(image_bytes: bytes) -> str:
    """Hash of the raw file bytes.

    Kept only as a legacy fallback: fixtures generated before the switch to
    pixel-based keys are still found.
    """
    return hashlib.sha256(image_bytes).hexdigest()[:16]


def image_key(image_bytes: bytes) -> str:
    """Stable identity for an image, used to look up its OCR fixture.

    Hashes the DECODED PIXELS, not the file bytes. A PNG re-encoded by a
    different Pillow version, an image-optimising file sync, or a transfer tool
    is byte-for-byte different but pixel-for-pixel identical — and the OCR
    boxes are still valid for it. Keying on file bytes made the seeded demo
    break the moment anything touched the file; keying on pixels does not.

    Falls back to the file hash if the bytes cannot be decoded as an image.
    """
    try:
        import io

        from PIL import Image, ImageOps

        with Image.open(io.BytesIO(image_bytes)) as opened:
            opened.load()
            image = ImageOps.exif_transpose(opened) or opened
            rgb = image.convert("RGB")
            digest = hashlib.sha256()
            digest.update(f"{rgb.width}x{rgb.height}|".encode())
            digest.update(rgb.tobytes())
            return digest.hexdigest()[:16]
    except Exception:
        return file_key(image_bytes)


# ---------------------------------------------------------------------------
# Fixture engine
# ---------------------------------------------------------------------------

class FixtureOcrEngine:
    """Serves committed OCR output for known demo images.

    Fixture files live in ``data/fixtures/ocr/`` and are keyed by the sha256
    prefix of the *original* image bytes, with an ``index.json`` mapping
    friendly names to keys.
    """

    name = "fixture"

    def __init__(self, fixtures_dir: Path | None = None) -> None:
        self.fixtures_dir = Path(fixtures_dir or config.OCR_FIXTURES_DIR)

    def _path_for(self, key: str) -> Path:
        return self.fixtures_dir / f"{key}.json"

    def _resolve(self, image_bytes: bytes) -> Path | None:
        """Find this image's fixture: pixel key first, legacy file key second."""
        for key in (image_key(image_bytes), file_key(image_bytes)):
            path = self._path_for(key)
            if path.is_file():
                return path
        return None

    def has_fixture(self, image_bytes: bytes) -> bool:
        return self._resolve(image_bytes) is not None

    def available(self) -> bool:
        return self.fixtures_dir.is_dir()

    def run(self, image_bytes: bytes) -> OcrResult:
        path = self._resolve(image_bytes)
        if path is None:
            return OcrResult(
                engine=self.name,
                unavailable_reason=(
                    f"No OCR fixture committed for image {image_key(image_bytes)}."
                ),
            )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return OcrResult(
                engine=self.name, unavailable_reason=f"Unreadable OCR fixture: {exc}"
            )

        lines = [
            OcrLine(
                text=str(entry.get("text", "")),
                bbox=[float(v) for v in entry.get("bbox", [0, 0, 0, 0])],
                confidence=float(entry.get("confidence", 0.0)),
            )
            for entry in payload.get("lines", [])
            if str(entry.get("text", "")).strip()
        ]
        return OcrResult(engine=payload.get("engine", self.name), lines=lines)


# ---------------------------------------------------------------------------
# Tesseract engine
# ---------------------------------------------------------------------------

class TesseractOcrEngine:
    """Real OCR. Optional — absence is handled, never fatal."""

    name = "tesseract"

    def __init__(self) -> None:
        self._checked = False
        self._ok = False
        self._reason: str | None = None

    def _probe(self) -> None:
        if self._checked:
            return
        self._checked = True
        try:
            import pytesseract  # noqa: F401
        except ImportError:
            self._reason = "pytesseract is not installed."
            return
        try:
            import pytesseract

            pytesseract.get_tesseract_version()
        except Exception as exc:  # binary missing or not on PATH
            self._reason = f"Tesseract binary unavailable: {exc}"
            return
        self._ok = True

    def available(self) -> bool:
        self._probe()
        return self._ok

    def run(self, image_bytes: bytes) -> OcrResult:
        self._probe()
        if not self._ok:
            return OcrResult(engine=self.name, unavailable_reason=self._reason)

        import io

        import pytesseract
        from PIL import Image

        with Image.open(io.BytesIO(image_bytes)) as opened:
            opened.load()
            image = opened.convert("RGB")

        data = pytesseract.image_to_data(
            image, output_type=pytesseract.Output.DICT, config="--psm 6"
        )

        # Group words into lines using Tesseract's own hierarchy.
        grouped: dict[tuple[int, int, int, int], list[int]] = {}
        for index, text in enumerate(data["text"]):
            if not str(text).strip():
                continue
            key = (
                data["page_num"][index],
                data["block_num"][index],
                data["par_num"][index],
                data["line_num"][index],
            )
            grouped.setdefault(key, []).append(index)

        lines: list[OcrLine] = []
        for key in sorted(grouped):
            indices = grouped[key]
            words = [str(data["text"][i]).strip() for i in indices]
            confidences = []
            for i in indices:
                try:
                    value = float(data["conf"][i])
                except (TypeError, ValueError):
                    continue
                if value >= 0:
                    confidences.append(value / 100.0)
            left = min(data["left"][i] for i in indices)
            top = min(data["top"][i] for i in indices)
            right = max(data["left"][i] + data["width"][i] for i in indices)
            bottom = max(data["top"][i] + data["height"][i] for i in indices)
            lines.append(
                OcrLine(
                    text=" ".join(words),
                    bbox=[float(left), float(top), float(right - left), float(bottom - top)],
                    confidence=round(sum(confidences) / len(confidences), 4)
                    if confidences
                    else 0.0,
                )
            )

        if not lines:
            return OcrResult(
                engine=self.name,
                unavailable_reason="OCR produced no readable text.",
                coordinate_space="processed",
            )
        return OcrResult(engine=self.name, lines=lines, coordinate_space="processed")


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

_fixture_engine = FixtureOcrEngine()
_tesseract_engine = TesseractOcrEngine()


def describe_active_engine() -> str:
    """Used by /health so the team can see which engine a machine will use."""
    if config.FORCE_FIXTURE_OCR:
        return "fixture (forced)"
    if _tesseract_engine.available():
        return "fixture + tesseract"
    return "fixture only (tesseract unavailable)"


def run_ocr(original_bytes: bytes, processed_bytes: bytes) -> OcrResult:
    """Run the best available engine for this image.

    Fixtures win when one exists, so a seeded demo case is byte-for-byte
    reproducible even on a machine that does have Tesseract installed.
    """
    if _fixture_engine.has_fixture(original_bytes):
        result = _fixture_engine.run(original_bytes)
        if result.available:
            return result

    if config.FORCE_FIXTURE_OCR:
        return OcrResult(
            engine="fixture",
            unavailable_reason=(
                "Fixture OCR is forced and no fixture exists for this image."
            ),
        )

    if _tesseract_engine.available():
        return _tesseract_engine.run(processed_bytes)

    return OcrResult(
        engine="none",
        unavailable_reason=(
            "No OCR engine available: this image has no committed fixture and "
            "Tesseract is not installed. Extraction routed to review."
        ),
    )
