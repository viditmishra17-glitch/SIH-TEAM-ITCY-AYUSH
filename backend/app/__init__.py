"""
TriVerify backend.

Layout:

    app/core/      configuration and the database engine/session
    app/models/    SQLAlchemy ORM — the frozen data contract
    app/schemas/   Pydantic — the frozen API response contract
    app/routers/   FastAPI endpoints (thin)
    app/services/  orchestration: ingest, present, report
    app/engine/    the deterministic verification core (pure, no I/O)
    app/pipeline/  image preprocessing, OCR, extraction, normalization, adapters
"""

__version__ = "1.0.0"
