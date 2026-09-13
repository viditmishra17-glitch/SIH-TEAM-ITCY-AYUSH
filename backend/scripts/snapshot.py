"""
Create a recoverable snapshot of the demo database and cached sources.

Build Manual section 11: "At every checkpoint, merge to main, run the full
smoke test, and create a recoverable snapshot."

Run from the backend/ directory:  python scripts/snapshot.py
"""

from __future__ import annotations

import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core import config  # noqa: E402


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_dir = ROOT / "snapshots"
    out_dir.mkdir(exist_ok=True)
    archive = out_dir / f"triverify-snapshot-{stamp}.zip"

    included = 0
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        db_file = ROOT / "triverify.db"
        if db_file.is_file():
            zf.write(db_file, "triverify.db")
            included += 1

        for folder in (config.GOLDEN_CASES_DIR, config.OCR_FIXTURES_DIR,
                       config.LISTINGS_DIR, config.OFFICIAL_DIR, config.IMAGES_DIR):
            if not folder.is_dir():
                continue
            for path in sorted(folder.rglob("*")):
                if path.is_file():
                    zf.write(path, str(path.relative_to(ROOT)))
                    included += 1

    size_kb = archive.stat().st_size / 1024
    print(f"Snapshot written: {archive.relative_to(ROOT)}")
    print(f"  {included} file(s), {size_kb:.0f} KB")
    print("\nRestore with:  python scripts/snapshot.py --restore <zip>")
    return 0


def restore(archive: str) -> int:
    path = Path(archive)
    if not path.is_file():
        print(f"No such snapshot: {archive}", file=sys.stderr)
        return 1
    with zipfile.ZipFile(path) as zf:
        zf.extractall(ROOT)
    print(f"Restored {path.name} into {ROOT}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--restore":
        raise SystemExit(restore(sys.argv[2]))
    raise SystemExit(main())
