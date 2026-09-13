"""
Central configuration. Everything is environment-driven so the same code runs
locally (SQLite, offline) and in production (Render + Supabase Postgres).

No secrets live in this file — see .env.example.
"""

from __future__ import annotations

import os
from pathlib import Path

try:  # optional convenience, never required
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv(*_args, **_kwargs):  # type: ignore[misc]
        return False

#: The backend/ directory. This file lives at backend/app/core/config.py, so
#: three levels up is the backend root that owns data/, reports/ and .env.
BACKEND_DIR = Path(__file__).resolve().parents[2]

#: The repository root (contains backend/ and frontend/).
PROJECT_ROOT = BACKEND_DIR.parent

#: Kept as an alias so existing references keep working.
ROOT_DIR = BACKEND_DIR

load_dotenv(BACKEND_DIR / ".env")


def _flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

DATA_DIR = Path(os.environ.get("TRIVERIFY_DATA_DIR", ROOT_DIR / "data"))
IMAGES_DIR = DATA_DIR / "images"
CROPS_DIR = DATA_DIR / "crops"
RAW_DIR = DATA_DIR / "raw"
LISTINGS_DIR = RAW_DIR / "listings"
OFFICIAL_DIR = RAW_DIR / "official"
FIXTURES_DIR = DATA_DIR / "fixtures"
GOLDEN_CASES_DIR = FIXTURES_DIR / "golden_cases"
OCR_FIXTURES_DIR = FIXTURES_DIR / "ocr"
REPORTS_DIR = Path(os.environ.get("TRIVERIFY_REPORTS_DIR", ROOT_DIR / "reports"))
#: The React bundle built by Vite. Lives outside backend/ because the frontend
#: is deployed separately to Vercel; FastAPI serves it locally as a convenience
#: so the demo needs no Node.
WEB_DIST_DIR = Path(
    os.environ.get("TRIVERIFY_WEB_DIST", PROJECT_ROOT / "frontend" / "dist")
)


def ensure_runtime_dirs() -> None:
    """Create writable directories. Safe to call repeatedly.

    On Render the filesystem is ephemeral, so these are scratch only — all
    durable evidence lives in the database.
    """
    for path in (CROPS_DIR, REPORTS_DIR):
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:  # read-only filesystem — non-fatal
            pass


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

#: Default is a local SQLite file so a clean clone works with no services
#: running. Production sets DATABASE_URL to the Supabase connection string.
DEFAULT_SQLITE_URL = f"sqlite:///{(ROOT_DIR / 'triverify.db').as_posix()}"
DATABASE_URL = os.environ.get("DATABASE_URL") or DEFAULT_SQLITE_URL

SQL_ECHO = _flag("TRIVERIFY_SQL_ECHO", False)

# ---------------------------------------------------------------------------
# Engine behaviour
# ---------------------------------------------------------------------------

#: Below this OCR confidence a field becomes REVIEW instead of being trusted.
#: "Unknown is not compliant" (Build Manual section 1).
CONFIDENCE_THRESHOLD = _float("TRIVERIFY_CONFIDENCE_THRESHOLD", 0.65)

#: Confidence at or above which a mismatch is treated as reliable enough to FAIL.
FAIL_CONFIDENCE_THRESHOLD = _float("TRIVERIFY_FAIL_CONFIDENCE_THRESHOLD", 0.70)

#: Money values within this many rupees are treated as equal (rounding noise).
MONEY_TOLERANCE = _float("TRIVERIFY_MONEY_TOLERANCE", 0.01)

#: Relative tolerance for quantity comparison (0.5% absorbs unit conversion noise).
QUANTITY_REL_TOLERANCE = _float("TRIVERIFY_QUANTITY_REL_TOLERANCE", 0.005)

#: Minimum token-overlap ratio for two normalized names to be "the same entity".
NAME_MATCH_THRESHOLD = _float("TRIVERIFY_NAME_MATCH_THRESHOLD", 0.6)

# ---------------------------------------------------------------------------
# External sources
# ---------------------------------------------------------------------------

#: OFF by default. The demo must never depend on the network
#: (Build Manual section 12 — fallback matrix).
LIVE_SOURCES_ENABLED = _flag("TRIVERIFY_LIVE_SOURCES", False)

#: Force the fixture OCR engine even when Tesseract is installed. Used by tests
#: so golden cases stay deterministic.
FORCE_FIXTURE_OCR = _flag("TRIVERIFY_FORCE_FIXTURE_OCR", False)

# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

APP_NAME = "TriVerify"
APP_VERSION = "1.0.0"

#: Comma-separated list of allowed browser origins. "*" during the hackathon;
#: set this to the Vercel domain in production.
CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("TRIVERIFY_CORS_ORIGINS", "*").split(",")
    if origin.strip()
]

MAX_UPLOAD_BYTES = int(os.environ.get("TRIVERIFY_MAX_UPLOAD_BYTES", 12 * 1024 * 1024))

#: The rule set version stamped onto every case, so a result can always be
#: traced back to the rules that produced it (Build Manual section 18).
RULESET_VERSION = os.environ.get("TRIVERIFY_RULESET_VERSION", "triverify-rules-v1")
