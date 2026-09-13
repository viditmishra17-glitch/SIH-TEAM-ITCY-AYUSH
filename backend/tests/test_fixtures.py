"""
Fixture robustness.

Regression cover for a real failure: the demo images were re-encoded in
transit (identical pixels, different PNG bytes), which broke an OCR-fixture
lookup keyed on the raw file hash. Seeding then failed with "No OCR fixture
for ...".

Two independent defences are tested here:

1. The fixture key is derived from decoded PIXELS, so any lossless re-encode
   still resolves to the same fixture.
2. Every golden case carries its OCR lines inline, so `app.seed` can rebuild a
   missing fixture from scratch under whatever key the local image produces.
"""

from __future__ import annotations

import io
import json

import pytest
from PIL import Image

from app.core import config
from app.pipeline.ocr import FixtureOcrEngine, file_key, image_key


def _reencode(png_bytes: bytes, **save_kwargs) -> bytes:
    """Re-save a PNG with different encoder settings. Pixels are untouched."""
    with Image.open(io.BytesIO(png_bytes)) as opened:
        opened.load()
        image = opened.convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", **save_kwargs)
    return buffer.getvalue()


@pytest.fixture(scope="module")
def demo_images():
    paths = sorted(config.IMAGES_DIR.glob("*.png"))
    assert paths, "no demo images found — run: python scripts/make_demo_data.py"
    return paths


class TestPixelKeyIsEncodingIndependent:
    def test_recompression_does_not_change_the_key(self, demo_images):
        original = demo_images[0].read_bytes()
        recompressed = _reencode(original, optimize=False, compress_level=1)

        assert recompressed != original, "test is meaningless if bytes are unchanged"
        assert image_key(recompressed) == image_key(original)

    def test_the_raw_file_hash_does_change(self, demo_images):
        """Shows why the file hash was the wrong key."""
        original = demo_images[0].read_bytes()
        recompressed = _reencode(original, optimize=False, compress_level=1)
        assert file_key(recompressed) != file_key(original)

    def test_fixture_still_resolves_after_recompression(self, demo_images):
        engine = FixtureOcrEngine()
        for path in demo_images:
            original = path.read_bytes()
            assert engine.has_fixture(original), f"no fixture for {path.name}"

            recompressed = _reencode(original, optimize=False, compress_level=1)
            assert engine.has_fixture(recompressed), (
                f"{path.name} lost its fixture after re-encoding"
            )

            before = engine.run(original)
            after = engine.run(recompressed)
            assert after.available
            assert [line.text for line in after.lines] == [
                line.text for line in before.lines
            ]

    def test_different_images_get_different_keys(self, demo_images):
        keys = {image_key(p.read_bytes()) for p in demo_images}
        assert len(keys) == len(demo_images)

    def test_undecodable_bytes_fall_back_to_the_file_hash(self):
        junk = b"not an image at all"
        assert image_key(junk) == file_key(junk)


class TestGoldenCasesAreSelfContained:
    def test_every_golden_case_carries_inline_ocr_lines(self, golden_cases):
        """Without these, a missing fixture cannot be rebuilt."""
        for case in golden_cases:
            lines = case.get("ocr_lines")
            assert lines, f"{case['case_id']} has no inline ocr_lines"
            for line in lines:
                assert line["text"].strip()
                assert len(line["bbox"]) == 4
                assert 0.0 <= line["confidence"] <= 1.0

    def test_inline_lines_match_the_committed_fixture(self, golden_cases):
        engine = FixtureOcrEngine()
        for case in golden_cases:
            image_path = config.IMAGES_DIR / case["image"]["file"]
            result = engine.run(image_path.read_bytes())
            assert result.available, f"{case['case_id']}: {result.unavailable_reason}"
            assert [line.text for line in result.lines] == [
                line["text"] for line in case["ocr_lines"]
            ]

    def test_label_lines_and_ocr_lines_agree(self, golden_cases):
        """The rendered image must reflect the authored label text."""
        for case in golden_cases:
            authored = [line["text"] for line in case["label_lines"]]
            extracted = [line["text"] for line in case["ocr_lines"]]
            assert authored == extracted, f"{case['case_id']} label/OCR drift"


class TestSeedSelfHeals:
    def test_seed_rebuilds_a_missing_fixture(self, tmp_path, golden_cases, monkeypatch):
        """Delete every fixture, then prove app.seed can recreate them."""
        from app.seed import _materialize_fixtures

        empty = tmp_path / "ocr"
        empty.mkdir()
        monkeypatch.setattr(config, "OCR_FIXTURES_DIR", empty)

        for case in golden_cases:
            _materialize_fixtures(case)

        rebuilt = sorted(empty.glob("*.json"))
        assert len(rebuilt) == len(golden_cases)

        for path in rebuilt:
            payload = json.loads(path.read_text(encoding="utf-8"))
            assert payload["lines"]
            assert payload["coordinate_space"] == "original"

    def test_rebuilt_fixture_is_keyed_by_the_local_image(
        self, tmp_path, golden_cases, monkeypatch
    ):
        empty = tmp_path / "ocr"
        empty.mkdir()
        monkeypatch.setattr(config, "OCR_FIXTURES_DIR", empty)

        from app.seed import _materialize_fixtures

        case = golden_cases[0]
        _materialize_fixtures(case)

        expected = image_key((config.IMAGES_DIR / case["image"]["file"]).read_bytes())
        assert (empty / f"{expected}.json").is_file()
