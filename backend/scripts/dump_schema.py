"""Regenerate app/models/schema.sql from the SQLAlchemy models (PostgreSQL dialect).

The application creates its own tables; this file exists so the frozen schema
is reviewable in one place. Run from the backend/ directory:

    python scripts/dump_schema.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.models import Base  # noqa: E402


def main() -> int:
    lines = [
        "-- TriVerify schema (PostgreSQL dialect) — generated from app/models/",
        "-- Reference only: the application creates tables itself via SQLAlchemy.",
        "-- Regenerate:  python scripts/dump_schema.py",
        "",
    ]
    dialect = postgresql.dialect()
    for table in Base.metadata.sorted_tables:
        lines.append(str(CreateTable(table).compile(dialect=dialect)).strip() + ";")
        for index in table.indexes:
            lines.append(str(CreateIndex(index).compile(dialect=dialect)).strip() + ";")
        lines.append("")

    (ROOT / "app" / "models" / "schema.sql").write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote app/models/schema.sql ({len(Base.metadata.sorted_tables)} tables)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
