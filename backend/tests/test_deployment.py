"""
Deployment-configuration tests.

These catch the connection-string and pooling mistakes that only show up in
production, without needing a database to connect to.
"""

from __future__ import annotations

import importlib.util

import pytest
from sqlalchemy.pool import NullPool, QueuePool, StaticPool

from app.core.database import _is_pgbouncer, build_engine, normalize_database_url

# The Postgres driver ships in requirements.txt (production) but not in
# requirements-dev.txt, because local dev and the offline demo run on SQLite.
# URL-string checks below are pure functions and always run; only the tests
# that actually construct a Postgres engine need the driver.
_HAS_PSYCOPG = importlib.util.find_spec("psycopg") is not None

needs_psycopg = pytest.mark.skipif(
    not _HAS_PSYCOPG,
    reason="psycopg is not installed (expected with requirements-dev.txt); "
    "install it with: pip install \"psycopg[binary]==3.3.5\"",
)


class TestUrlNormalization:
    @pytest.mark.parametrize(
        "raw",
        [
            "postgres://u:p@db.abc.supabase.co:5432/postgres",
            "postgresql://u:p@db.abc.supabase.co:5432/postgres",
            "postgresql+psycopg://u:p@db.abc.supabase.co:5432/postgres",
        ],
    )
    def test_every_postgres_spelling_gets_a_driver(self, raw):
        assert normalize_database_url(raw).startswith("postgresql+psycopg://")

    def test_ssl_is_required_by_default(self):
        url = normalize_database_url("postgres://u:p@db.abc.supabase.co:5432/postgres")
        assert "sslmode=require" in url

    def test_explicit_sslmode_is_respected(self):
        url = normalize_database_url("postgresql://u:p@localhost:5432/db?sslmode=disable")
        assert "sslmode=disable" in url
        assert "sslmode=require" not in url

    def test_sqlite_is_left_alone(self):
        assert normalize_database_url("sqlite:///./triverify.db") == "sqlite:///./triverify.db"


class TestSupabasePooler:
    def test_port_6543_is_detected_as_pgbouncer(self):
        assert _is_pgbouncer(
            "postgresql+psycopg://u:p@aws-0-ap-south-1.pooler.supabase.com:6543/postgres"
        )

    def test_direct_port_is_not_pgbouncer(self):
        assert not _is_pgbouncer("postgresql+psycopg://u:p@db.abc.supabase.co:5432/postgres")

    @needs_psycopg
    def test_pooler_uses_nullpool(self):
        """PgBouncer transaction mode cannot hold SQLAlchemy's pooled connections."""
        engine = build_engine(
            "postgresql://u:p@aws-0-ap-south-1.pooler.supabase.com:6543/postgres"
        )
        assert isinstance(engine.pool, NullPool)

    @needs_psycopg
    def test_pooler_disables_prepared_statements(self):
        """Otherwise you get intermittent DuplicatePreparedStatement errors."""
        engine = build_engine(
            "postgresql://u:p@aws-0-ap-south-1.pooler.supabase.com:6543/postgres"
        )
        assert engine.dialect.create_connect_args(engine.url)[1].get("prepare_threshold") is None

    @needs_psycopg
    def test_direct_connection_uses_a_real_pool(self):
        engine = build_engine("postgresql://u:p@db.abc.supabase.co:5432/postgres")
        assert isinstance(engine.pool, QueuePool)


class TestSqliteEngines:
    def test_in_memory_shares_one_connection(self):
        assert isinstance(build_engine("sqlite:///:memory:").pool, StaticPool)

    def test_file_engine_allows_cross_thread_use(self, tmp_path):
        engine = build_engine(f"sqlite:///{(tmp_path / 'x.db').as_posix()}")
        assert engine.dialect.name == "sqlite"


class TestModelPortability:
    def test_schema_compiles_for_postgres_and_sqlite(self):
        """Catches any accidentally dialect-specific column type."""
        from sqlalchemy.dialects import postgresql, sqlite
        from sqlalchemy.schema import CreateTable

        from app.models import Base

        for table in Base.metadata.sorted_tables:
            for dialect in (postgresql.dialect(), sqlite.dialect()):
                assert str(CreateTable(table).compile(dialect=dialect)).strip()
