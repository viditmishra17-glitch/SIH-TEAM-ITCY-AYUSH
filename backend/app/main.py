"""
TriVerify API.

Small on purpose (Build Manual section 5): a handful of stable endpoints
rather than a sprawling API. Also serves the prebuilt React bundle when one is
present, so the whole demo runs from a single process with no Node required.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select, text

from app.core import config
from app.core.database import (
    get_session_factory,
    init_db,
    normalize_database_url,
)
from app.engine.classify import CLASSIFICATIONS
from app.engine.rules import ALL_RULES
from app.models import Case
from app.pipeline.ocr import describe_active_engine
from app.routers import cases, evidence, reports
from app.schemas import HealthResponse

log = logging.getLogger("triverify")

#: Path prefixes owned by the API. The SPA catch-all must never shadow them.
_API_PREFIXES = {
    "cases",
    "health",
    "rules",
    "classifications",
    "docs",
    "redoc",
    "openapi.json",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.ensure_runtime_dirs()
    try:
        init_db()
    except Exception as exc:  # a dead DB should not hide the error behind a 500 storm
        log.error("Database initialisation failed: %s", exc)
    yield


app = FastAPI(
    title=f"{config.APP_NAME} API",
    version=config.APP_VERSION,
    description=(
        "Three-layer Legal Metrology compliance verification: physical label vs "
        "seller listing vs official registered declaration."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(cases.router)
app.include_router(evidence.router)
app.include_router(reports.router)


@app.get("/health", response_model=HealthResponse, tags=["ops"])
def health() -> HealthResponse:
    """Health check for the demo and for Render's probe."""
    database_ok = True
    golden = 0
    try:
        with get_session_factory()() as session:
            session.execute(text("SELECT 1"))
            golden = len(
                session.execute(select(Case).where(Case.is_golden.is_(True)))
                .scalars()
                .all()
            )
    except Exception as exc:
        log.warning("Health check database probe failed: %s", exc)
        database_ok = False

    url = normalize_database_url(config.DATABASE_URL)
    dialect = url.split("://", 1)[0]

    return HealthResponse(
        status="ok" if database_ok else "degraded",
        app=config.APP_NAME,
        version=config.APP_VERSION,
        database=dialect,
        database_ok=database_ok,
        ocr_engine=describe_active_engine(),
        live_sources_enabled=config.LIVE_SOURCES_ENABLED,
        ruleset_version=config.RULESET_VERSION,
        golden_cases=golden,
        # The demo is offline-ready when seeded cases exist and nothing needs
        # the network to render them.
        offline_ready=database_ok and golden > 0 and not config.LIVE_SOURCES_ENABLED,
    )


@app.get("/rules", tags=["ops"])
def list_rules() -> JSONResponse:
    """The configured rule set, so a judge can read what actually decides."""
    return JSONResponse(
        {
            "ruleset_version": config.RULESET_VERSION,
            "confidence_threshold": config.CONFIDENCE_THRESHOLD,
            "fail_confidence_threshold": config.FAIL_CONFIDENCE_THRESHOLD,
            "rules": [
                {
                    "rule_id": rule.rule_id,
                    "rule_type": rule.rule_type,
                    "field_name": rule.field_name,
                    "compares": [rule.left, rule.right] if rule.left else None,
                    "any_of": list(rule.any_of) or None,
                    "severity": rule.severity,
                    "explanation_template": rule.explanation_template,
                    "legal_reference": rule.legal_reference,
                    "active": rule.active,
                }
                for rule in ALL_RULES
            ],
        }
    )


@app.get("/classifications", tags=["ops"])
def list_classifications() -> JSONResponse:
    return JSONResponse(
        {
            "classifications": [
                {
                    "code": info.code,
                    "title": info.title,
                    "trigger": info.trigger,
                    "tone": info.tone,
                }
                for info in CLASSIFICATIONS.values()
            ]
        }
    )


# ---------------------------------------------------------------------------
# Static SPA (optional)
# ---------------------------------------------------------------------------

_INDEX = config.WEB_DIST_DIR / "index.html"

if _INDEX.is_file():
    from fastapi.staticfiles import StaticFiles

    assets = config.WEB_DIST_DIR / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @app.get("/", include_in_schema=False)
    def spa_root() -> FileResponse:
        return FileResponse(_INDEX)

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_catch_all(full_path: str):
        """Serve the SPA for unknown paths, but never mask an API 404.

        The frontend uses hash routing, so this only has to cover direct hits
        on static files and stray URLs.
        """
        root = full_path.split("/", 1)[0]
        if root in _API_PREFIXES:
            return JSONResponse({"detail": "Not found."}, status_code=404)

        candidate = (config.WEB_DIST_DIR / full_path).resolve()
        try:
            candidate.relative_to(config.WEB_DIST_DIR.resolve())
        except ValueError:
            return JSONResponse({"detail": "Not found."}, status_code=404)
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_INDEX)

else:  # pragma: no cover - only when the bundle was not built

    @app.get("/", include_in_schema=False)
    def api_root() -> JSONResponse:
        return JSONResponse(
            {
                "app": config.APP_NAME,
                "version": config.APP_VERSION,
                "message": (
                    "API is running. The React bundle was not found at "
                    f"{config.WEB_DIST_DIR}. Build it with `npm run build` in frontend/, "
                    "or run the Vite dev server."
                ),
                "docs": "/docs",
                "health": "/health",
            }
        )
