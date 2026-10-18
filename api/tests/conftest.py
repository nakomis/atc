"""Postgres test harness: one container per session, Plane's tables plus the atc role."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from plane_factory import PLANE_TABLES, PlaneFactory

try:  # testcontainers >= 4.13 moved the module; the old path still works but warns.
    from testcontainers.community.postgres import PostgresContainer
except ImportError:  # pragma: no cover
    from testcontainers.postgres import PostgresContainer

from atc import db
from atc.app import create_app
from atc.settings import Settings

FIXTURES = Path(__file__).parent / "fixtures"
POSTGRES_IMAGE = "postgres:15.19-alpine"


def _grants_password() -> str:
    """The atc test password, read from grants.sql so the two cannot drift."""
    sql = (FIXTURES / "grants.sql").read_text()
    match = re.search(r"ALTER ROLE atc WITH LOGIN PASSWORD '([0-9a-f]{64})'", sql)
    if match is None:
        raise RuntimeError("tests/fixtures/grants.sql must set a 64-hex password for atc")
    return match.group(1)


ATC_PASSWORD = _grants_password()
# The rows ATC writes; column_def and schema_version are migration data and survive.
ATC_DATA_TABLES = ("atc.project", "atc.module", "atc.work_item")


@pytest.fixture(scope="session")
def pg_urls() -> Iterator[dict[str, str]]:
    # The superuser is named `plane` so it stands in for Plane's own role, as on Luke.
    with PostgresContainer(POSTGRES_IMAGE, username="plane", password="plane", dbname="plane") as pg:
        host = pg.get_container_host_ip()
        port = pg.get_exposed_port(5432)
        urls = {
            "admin": f"postgresql://plane:plane@{host}:{port}/plane",
            "atc": f"postgresql://atc:{ATC_PASSWORD}@{host}:{port}/plane",
        }
        apply_plane_fixtures(urls["admin"])
        yield urls


def apply_plane_fixtures(admin_url: str) -> None:
    """Create Plane's tables and the atc role, schema and grants in the database at `admin_url`."""
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute((FIXTURES / "plane_schema.sql").read_text())
        conn.execute((FIXTURES / "grants.sql").read_text())


@pytest.fixture
def fresh_db(pg_urls: dict[str, str]) -> Iterator[dict[str, str]]:
    """A throwaway database in the same container, set up like `plane` but never migrated."""
    name = "atc_fresh"
    with psycopg.connect(pg_urls["admin"], autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")
        conn.execute(f"CREATE DATABASE {name}")
    urls = {role: url.rsplit("/", 1)[0] + f"/{name}" for role, url in pg_urls.items()}
    apply_plane_fixtures(urls["admin"])
    try:
        yield urls
    finally:
        with psycopg.connect(pg_urls["admin"], autocommit=True) as conn:
            conn.execute(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")


def _reset(admin_url: str) -> None:
    """Empty Plane's tables and ATC's data tables (the latter only once migrated)."""
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute("TRUNCATE " + ", ".join(f"public.{t}" for t in PLANE_TABLES))
        present = [t for t in ATC_DATA_TABLES if conn.execute("SELECT to_regclass(%s)", (t,)).fetchone()[0]]
        if present:
            conn.execute("TRUNCATE " + ", ".join(present))


@pytest.fixture(scope="session")
def migrated(pg_urls: dict[str, str]) -> str:
    pool = db.open_pool(pg_urls["atc"])
    try:
        db.migrate(pool)
    finally:
        pool.close()
    return pg_urls["atc"]


@pytest.fixture
def atc_conn(pg_urls: dict[str, str], migrated: str) -> Iterator[psycopg.Connection]:
    _reset(pg_urls["admin"])
    with psycopg.connect(migrated, autocommit=True) as conn:
        yield conn


@pytest.fixture
def plane(pg_urls: dict[str, str]) -> Iterator[PlaneFactory]:
    _reset(pg_urls["admin"])
    with psycopg.connect(pg_urls["admin"], autocommit=True) as conn:
        yield PlaneFactory(conn)


@pytest.fixture
def client(pg_urls: dict[str, str]) -> Iterator[TestClient]:
    _reset(pg_urls["admin"])
    app = create_app(Settings(database_url=pg_urls["atc"], reconcile_seconds=0))
    with TestClient(app) as c:
        yield c
