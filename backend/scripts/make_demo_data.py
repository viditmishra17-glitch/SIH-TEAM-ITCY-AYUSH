"""
Generate the demo artefacts from the golden-case definitions.

For every ``data/fixtures/golden_cases/*.json`` this writes:

* ``data/images/<file>.png``          — a synthetic packaged-commodity label
* ``data/fixtures/ocr/<hash>.json``   — OCR output whose bounding boxes are the
                                        exact pixel rectangles the text was
                                        drawn into
* ``data/raw/listings/<id>.json``     — cached seller snapshot
* ``data/raw/official/<id>.json``     — cached official snapshot (when present)

The OCR fixture is keyed by the sha256 of the generated PNG, so the fixture and
the image can never drift apart: regenerating one regenerates the other.

Run from the backend/ directory:  python scripts/make_demo_data.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core import config  # noqa: E402
from app.pipeline.adapters.base import FixtureAdapter  # noqa: E402
from app.pipeline.ocr import image_key  # noqa: E402

CANVAS_WIDTH = 940
MARGIN_X = 56
MARGIN_TOP = 34
MARGIN_BOTTOM = 44
LINE_GAP = 16

THEMES: dict[str, dict[str, tuple[int, int, int]]] = {
    "cream": {"bg": (247, 241, 227), "fg": (38, 34, 28), "accent": (150, 108, 44)},
    "amber": {"bg": (250, 240, 219), "fg": (44, 33, 18), "accent": (176, 112, 30)},
    "slate": {"bg": (233, 236, 240), "fg": (28, 33, 41), "accent": (58, 82, 120)},
    "olive": {"bg": (240, 243, 230), "fg": (32, 40, 27), "accent": (90, 118, 52)},
}

_FONT_CANDIDATES = {
    False: [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/Library/Fonts/Arial.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ],
    True: [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ],
}


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for candidate in _FONT_CANDIDATES[bold]:
        path = Path(candidate)
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                continue
    # Last resort: the bitmap default. Images stay usable, just plainer.
    return ImageFont.load_default()


def render_label(case: dict) -> tuple[bytes, list[dict]]:
    """Draw the label and return (png_bytes, ocr_lines).

    Bounding boxes are recorded from the real draw positions, so clicking a
    field in the UI highlights exactly the pixels that produced it.
    """
    image_spec = case.get("image", {})
    theme = THEMES.get(image_spec.get("theme", "cream"), THEMES["cream"])
    lines = case.get("label_lines", [])

    header_font = load_font(15, bold=True)

    # Measure first so the canvas is exactly as tall as the content.
    measure = Image.new("RGB", (10, 10))
    measure_draw = ImageDraw.Draw(measure)

    layout: list[tuple[dict, ImageFont.ImageFont, int]] = []
    y = MARGIN_TOP + 34  # room for the header strip
    for spec in lines:
        font = load_font(int(spec.get("size", 20)), bold=bool(spec.get("bold")))
        bbox = measure_draw.textbbox((0, 0), str(spec.get("text", "")), font=font)
        height = bbox[3] - bbox[1]
        layout.append((spec, font, y))
        y += height + LINE_GAP

    canvas_height = y + MARGIN_BOTTOM

    image = Image.new("RGB", (CANVAS_WIDTH, canvas_height), theme["bg"])
    draw = ImageDraw.Draw(image)

    # Header strip + border, so it reads as a package panel rather than a memo.
    draw.rectangle([(0, 0), (CANVAS_WIDTH, 26)], fill=theme["accent"])
    draw.text(
        (MARGIN_X, 6),
        image_spec.get("title", "PACKAGED COMMODITY LABEL"),
        font=header_font,
        fill=(255, 255, 255),
    )
    draw.rectangle(
        [(6, 6), (CANVAS_WIDTH - 7, canvas_height - 7)], outline=theme["accent"], width=2
    )

    ocr_lines: list[dict] = []
    degraded_boxes: list[tuple[int, int, int, int]] = []

    for spec, font, top in layout:
        text = str(spec.get("text", ""))
        colour = theme["fg"]
        if spec.get("degraded"):
            # Wash the text out so the picture matches the low confidence the
            # fixture reports. Judges notice when those two disagree.
            colour = tuple(
                int(fg * 0.45 + bg * 0.55)
                for fg, bg in zip(theme["fg"], theme["bg"])
            )
        draw.text((MARGIN_X, top), text, font=font, fill=colour)

        box = draw.textbbox((MARGIN_X, top), text, font=font)
        if spec.get("degraded"):
            degraded_boxes.append(box)

        ocr_lines.append(
            {
                "text": text,
                "bbox": [
                    float(box[0]),
                    float(box[1]),
                    float(box[2] - box[0]),
                    float(box[3] - box[1]),
                ],
                "confidence": float(spec.get("confidence", 0.9)),
            }
        )

    # Physically blur the degraded region so the low confidence is visible.
    for box in degraded_boxes:
        pad = 6
        region = (
            max(0, box[0] - pad),
            max(0, box[1] - pad),
            min(CANVAS_WIDTH, box[2] + pad),
            min(canvas_height, box[3] + pad),
        )
        patch = image.crop(region).filter(ImageFilter.GaussianBlur(radius=1.6))
        image.paste(patch, region)

    import io

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue(), ocr_lines


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def build_case(case_path: Path) -> dict:
    case = json.loads(case_path.read_text(encoding="utf-8"))
    case_id = case["case_id"]
    identifier = case["product"]["identifier"]

    png_bytes, ocr_lines = render_label(case)

    image_path = config.IMAGES_DIR / case["image"]["file"]
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(png_bytes)

    key = image_key(png_bytes)
    write_json(
        config.OCR_FIXTURES_DIR / f"{key}.json",
        {
            "engine": "fixture",
            "case_id": case_id,
            "image_file": case["image"]["file"],
            "coordinate_space": "original",
            "lines": ocr_lines,
        },
    )

    # Also record the OCR lines inside the golden case itself. The case file is
    # then a complete, self-contained definition, and `python -m app.seed` can
    # rebuild a missing fixture under whatever key the local image produces —
    # no dependency on this script having been run on this machine.
    case["ocr_lines"] = ocr_lines
    write_json(case_path, case)

    fixture_key = FixtureAdapter._key(identifier)
    wrote_official = False
    if case.get("listing"):
        write_json(config.LISTINGS_DIR / f"{fixture_key}.json", case["listing"])
    if case.get("official"):
        write_json(config.OFFICIAL_DIR / f"{fixture_key}.json", case["official"])
        wrote_official = True

    return {
        "case_id": case_id,
        "image": str(image_path.relative_to(config.ROOT_DIR)),
        "ocr_key": key,
        "identifier": identifier,
        "official": wrote_official,
    }


def main() -> int:
    case_files = sorted(config.GOLDEN_CASES_DIR.glob("*.json"))
    if not case_files:
        print(f"No golden cases found in {config.GOLDEN_CASES_DIR}", file=sys.stderr)
        return 1

    for path in case_files:
        info = build_case(path)
        official = "official ✓" if info["official"] else "official ✗ (deliberate)"
        print(
            f"{info['case_id']}  image={info['image']}  ocr={info['ocr_key']}  "
            f"id={info['identifier']}  {official}"
        )
    print(f"\nGenerated {len(case_files)} demo case(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
