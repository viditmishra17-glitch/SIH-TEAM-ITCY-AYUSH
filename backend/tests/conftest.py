"""
Shared test fixtures.

Every test runs against a throwaway SQLite database and the fixture OCR engine,
so the suite is fully deterministic and needs no services, no network and no
Tesseract install.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Must be set before config is imported anywhere.
os.environ["TRIVERIFY_FORCE_FIXTURE_OCR"] = "1"
os.environ["TRIVERIFY_LIVE_SOURCES"] = "0"


@pytest.fixture(scope="session", autouse=True)
def _database(tmp_path_factory):
    """Point the whole process at a temporary database for the test session."""
    from app.core import config
    from app.core import database as db_session

    db_path = tmp_path_factory.mktemp("triverify") / "test.db"
    url = f"sqlite:///{db_path.as_posix()}"
    config.DATABASE_URL = url
    db_session.configure(url)
    db_session.init_db(drop=True)
    yield url


@pytest.fixture(scope="session")
def seeded(_database):
    """Seed the four golden cases once for the whole session."""
    from app.seed import seed

    return seed(verbose=False)


@pytest.fixture()
def session(_database):
    from app.core.database import get_session_factory

    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="session")
def client(seeded):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def golden_cases():
    import json

    from app.core import config

    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(config.GOLDEN_CASES_DIR.glob("*.json"))
    ]
