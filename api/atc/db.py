"""Connection pool and schema migrations for the `atc` schema."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from psycopg_pool import ConnectionPool

log = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_MIGRATION_NAME = re.compile(r"^(\d{3})_.+\.sql$")
# Arbitrary fixed key: concurrent starters (two replicas, a test and the app) queue on it.
MIGRATION_LOCK_KEY = 0x41544300


def open_pool(url: str) -> ConnectionPool:
    return ConnectionPool(conninfo=url, min_size=1, max_size=8, open=True)


def migrations(directory: Path = MIGRATIONS_DIR) -> list[tuple[int, Path]]:
    """The NNN_*.sql files in `directory`, in version order."""
    found = []
    for path in directory.iterdir():
        match = _MIGRATION_NAME.match(path.name)
        if match:
            found.append((int(match.group(1)), path))
    found.sort()
    versions = [v for v, _ in found]
    if len(set(versions)) != len(versions):
        raise ValueError(f"duplicate migration versions in {directory}")
    return found


def migrate(pool: ConnectionPool, directory: Path = MIGRATIONS_DIR) -> int:
    """Apply every migration above atc.schema_version, each in its own transaction.

    Each transaction takes a transaction-scoped advisory lock and re-reads the version
    under it, so concurrent callers apply each migration exactly once. Returns the
    schema version reached.
    """
    version = 0
    with pool.connection() as conn:
        for number, path in migrations(directory):
            with conn.transaction():
                conn.execute("SELECT pg_advisory_xact_lock(%s)", (MIGRATION_LOCK_KEY,))
                version = _current_version(conn)
                if number <= version:
                    continue
                log.info("applying migration %s", path.name)
                conn.execute(path.read_text())
                conn.execute("INSERT INTO atc.schema_version (version) VALUES (%s)", (number,))
                version = number
        if version == 0:
            version = _current_version(conn)
    return version


def _current_version(conn) -> int:
    if conn.execute("SELECT to_regclass('atc.schema_version')").fetchone()[0] is None:
        return 0
    return conn.execute("SELECT coalesce(max(version), 0) FROM atc.schema_version").fetchone()[0]
