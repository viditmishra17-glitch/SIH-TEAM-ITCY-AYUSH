"""
M1 — Image ingestion + preprocessing (Build Manual section 6).

JOB:        turn a product photo into stable input for OCR.
INPUT:      JPG/PNG bytes.
OUTPUT:     corrected image bytes + dimensions + quality score.
DONE WHEN:  the same demo image produces repeatable regions and a visible
            preprocessing preview.
CONSTRAINT: never destroy the original — both the original and the derived
            image are stored.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageFilter, ImageOps, ImageStat, UnidentifiedImageError

#: Long edge cap. Big enough for OCR, small enough to keep the demo snappy.
MAX_EDGE = 1600


class ImageDecodeError(ValueError):
    """Raised when the upload is not a decodable image."""


@dataclass(frozen=True)
class PreprocessResult:
    original_bytes: bytes
    original_size: tuple[int, int]
    processed_bytes: bytes
    processed_size: tuple[int, int]
    #: Scale factor applied to get from original to processed coordinates.
    scale: float
    #: 0..1 heuristic. Low scores justify routing extraction to REVIEW.
    quality_score: float
    content_type: str = "image/png"


def _sharpness(image: Image.Image) -> float:
    """Edge-energy proxy for focus. Higher is sharper."""
    edges = image.convert("L").filter(ImageFilter.FIND_EDGES)
    return float(ImageStat.Stat(edges).stddev[0])


def _contrast(image: Image.Image) -> float:
    return float(ImageStat.Stat(image.convert("L")).stddev[0])


def quality_score(image: Image.Image) -> float:
    """Combine resolution, contrast and sharpness into a 0..1 score."""
    width, height = image.size
    resolution = min(1.0, (min(width, height) / 600.0))
    contrast = min(1.0, _contrast(image) / 60.0)
    sharpness = min(1.0, _sharpness(image) / 28.0)
    score = 0.30 * resolution + 0.35 * contrast + 0.35 * sharpness
    return round(max(0.0, min(1.0, score)), 3)


def preprocess_image(data: bytes) -> PreprocessResult:
    """Decode, correct and normalize an uploaded image.

    Deterministic: the same bytes in always produce the same bytes out, which
    is what makes fixture-backed golden cases reproducible.
    """
    if not data:
        raise ImageDecodeError("Empty upload.")

    try:
        with Image.open(io.BytesIO(data)) as opened:
            opened.load()
            # Honour camera rotation before anything else, or every bbox is wrong.
            image = ImageOps.exif_transpose(opened)
            if image is None:
                image = opened
            image = image.convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise ImageDecodeError("Unsupported or corrupt image file.") from exc

    original_size = image.size

    scale = 1.0
    longest = max(image.size)
    if longest > MAX_EDGE:
        scale = MAX_EDGE / float(longest)
        new_size = (
            max(1, int(round(image.width * scale))),
            max(1, int(round(image.height * scale))),
        )
        image = image.resize(new_size, Image.LANCZOS)

    score = quality_score(image)

    # Gentle, order-dependent corrections. Deliberately conservative: an
    # aggressive filter can erase small print, which is exactly the print the
    # Legal Metrology checks care about.
    processed = image.filter(ImageFilter.MedianFilter(size=3))
    processed = ImageOps.autocontrast(processed, cutoff=1)
    processed = processed.filter(
        ImageFilter.UnsharpMask(radius=1.2, percent=110, threshold=3)
    )

    buffer = io.BytesIO()
    processed.save(buffer, format="PNG", optimize=True)

    return PreprocessResult(
        original_bytes=data,
        original_size=original_size,
        processed_bytes=buffer.getvalue(),
        processed_size=processed.size,
        scale=scale,
        quality_score=score,
    )


def crop_region(data: bytes, bbox: list[float] | tuple[float, ...], padding: int = 8) -> bytes:
    """Cut an evidence crop out of an image.

    ``bbox`` is ``[x, y, w, h]`` in the coordinate space of ``data``. The crop
    is clamped to the image, so a slightly out-of-range OCR box still produces
    a usable picture instead of an exception during a demo.
    """
    if not bbox or len(bbox) < 4:
        raise ValueError("bbox must be [x, y, w, h]")

    with Image.open(io.BytesIO(data)) as opened:
        opened.load()
        image = opened.convert("RGB")

    x, y, w, h = (float(v) for v in bbox[:4])
    left = max(0, int(x) - padding)
    top = max(0, int(y) - padding)
    right = min(image.width, int(x + w) + padding)
    bottom = min(image.height, int(y + h) + padding)

    if right <= left:
        right = min(image.width, left + 1)
    if bottom <= top:
        bottom = min(image.height, top + 1)

    crop = image.crop((left, top, right, bottom))

    # Upscale tiny crops so a judge can actually read them on a projector.
    if crop.width and crop.height and max(crop.size) < 320:
        factor = min(4.0, 320.0 / max(crop.size))
        crop = crop.resize(
            (max(1, int(crop.width * factor)), max(1, int(crop.height * factor))),
            Image.LANCZOS,
        )

    buffer = io.BytesIO()
    crop.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
