"""
Seed the deterministic demo cases.

Idempotent: re-running rebuilds every golden case from scratch, so the demo
database can always be restored to a known state in seconds.

Run from the backend/ directory:  python -m app.seed
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import select

from app.core import config
from app.services.case_service import create_case
from app.models import Case
from app.core.database import init_db, session_scope
from app.pipeline.adapters.base import FixtureAdapter
from app.pipeline.ocr import image_key


class SeedError(RuntimeError):
    pass


def _load_golden_cases() -> list[dict]:
    paths = sorted(config.GOLDEN_CASES_DIR.glob("*.json"))
    if not paths:
        raise SeedError(
            f"No golden cases found in {config.GOLDEN_CASES_DIR}. "
            "Run: python scripts/make_demo_data.py"
        )
    return [json.loads(path.read_text(encoding="utf-8")) for path in paths]


def _materialize_fixtures(case: dict) -> Path:
    """Make sure the OCR fixture and cached snapshots exist for this case.

    Self-healing: the OCR fixture is keyed by the hash of the image on disk, so
    if the image was regenerated with a different Pillow version the fixture is
    rewritten under the new key instead of silently missing.
    """
    image_path = config.IMAGES_DIR / case["image"]["file"]
    if not image_path.is_file():
        raise SeedError(
            f"Missing demo image {image_path}. Run: python scripts/make_demo_data.py"
        )

    image_bytes = image_path.read_bytes()
    key = image_key(image_bytes)
    fixture_path = config.OCR_FIXTURES_DIR / f"{key}.json"

    if not fixture_path.is_file():
        lines = case.get("ocr_lines")
        if not lines:
            raise SeedError(
                f"No OCR fixture for {image_path.name} (key {key}) and the golden case "
                "carries no inline OCR lines. Run: python scripts/make_demo_data.py"
            )
        fixture_path.parent.mkdir(parents=True, exist_ok=True)
        fixture_path.write_text(
            json.dumps(
                {
                    "engine": "fixture",
                    "case_id": case["case_id"],
                    "image_file": case["image"]["file"],
                    "coordinate_space": "original",
                    "lines": lines,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    identifier = case["product"]["identifier"]
    fixture_key = FixtureAdapter._key(identifier)
    if case.get("listing"):
        path = config.LISTINGS_DIR / f"{fixture_key}.json"
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(case["listing"], indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
    if case.get("official"):
        path = config.OFFICIAL_DIR / f"{fixture_key}.json"
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(case["official"], indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

    return image_path


def seed(verbose: bool = True) -> list[tuple[str, str, str]]:
    """(Re)create every golden case. Returns (case_id, expected, actual)."""
    config.ensure_runtime_dirs()
    init_db()

    results: list[tuple[str, str, str]] = []
    for case in _load_golden_cases():
        case_id = case["case_id"]
        image_path = _materialize_fixtures(case)

        with session_scope() as session:
            existing = session.execute(
                select(Case).where(Case.case_id == case_id)
            ).scalars().first()
            if existing is not None:
                session.delete(existing)
                session.flush()

            created = create_case(
                session,
                image_bytes=image_path.read_bytes(),
                filename=image_path.name,
                identifier=case["product"]["identifier"],
                product_hints={
                    "name": case["product"].get("name"),
                    "brand": case["product"].get("brand"),
                    "category": case["product"].get("category"),
                },
                case_id=case_id,
                is_golden=True,
            )
            actual = created.classification or "?"

        expected = case.get("expected_classification", "?")
        results.append((case_id, expected, actual))
        if verbose:
            mark = "OK  " if expected == actual else "FAIL"
            print(f"[{mark}] {case_id}  expected={expected}  actual={actual}")

    return results


def main() -> int:
    results = seed()
    mismatches = [r for r in results if r[1] != r[2]]
    print(f"\nSeeded {len(results)} golden case(s).")
    if mismatches:
        print("Classification mismatches:", file=sys.stderr)
        for case_id, expected, actual in mismatches:
            print(f"  {case_id}: expected {expected}, got {actual}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
