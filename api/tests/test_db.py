import shutil
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from atc import db
from atc.app import create_app
from atc.settings import Settings


def test_migrate_creates_atc_tables(pg_urls):
    pool = db.open_pool(pg_urls["atc"])
    try:
        assert db.migrate(pool) == 1
        assert db.migrate(pool) == 1  # idempotent
        with pool.connection() as c:
            keys = [r[0] for r in c.execute("SELECT key FROM atc.column_def ORDER BY position")]
    finally:
        pool.close()
    assert keys == ["backlog", "next", "in_progress"]


def test_migrate_applies_later_migrations_in_order_once(fresh_db, tmp_path):
    shutil.copy(db.MIGRATIONS_DIR / "001_init.sql", tmp_path / "001_init.sql")
    pool = db.open_pool(fresh_db["atc"])
    try:
        assert db.migrate(pool, tmp_path) == 1
        # Written out of order on purpose: 003 depends on 002, which depends on 001.
        (tmp_path / "003_more.sql").write_text("INSERT INTO atc.trail (step) VALUES (3);")
        (tmp_path / "002_trail.sql").write_text(
            "CREATE TABLE atc.trail (n serial PRIMARY KEY, step int NOT NULL);"
            " INSERT INTO atc.trail (step) VALUES (2);"
        )
        # 001 would fail on CREATE TABLE if re-run, so success also proves it is skipped.
        assert db.migrate(pool, tmp_path) == 3
        assert db.migrate(pool, tmp_path) == 3  # idempotent
        with pool.connection() as c:
            versions = [r[0] for r in c.execute("SELECT version FROM atc.schema_version ORDER BY version")]
            steps = [r[0] for r in c.execute("SELECT step FROM atc.trail ORDER BY n")]
    finally:
        pool.close()
    assert versions == [1, 2, 3]
    assert steps == [2, 3]


def test_failed_migration_rolls_back_and_keeps_the_version(fresh_db, tmp_path):
    shutil.copy(db.MIGRATIONS_DIR / "001_init.sql", tmp_path / "001_init.sql")
    (tmp_path / "002_broken.sql").write_text("CREATE TABLE atc.half (n int); SELECT no_such_function();")
    pool = db.open_pool(fresh_db["atc"])
    try:
        with pytest.raises(psycopg.errors.UndefinedFunction):
            db.migrate(pool, tmp_path)
        with pool.connection() as c:
            versions = [r[0] for r in c.execute("SELECT version FROM atc.schema_version")]
            half = c.execute("SELECT to_regclass('atc.half')").fetchone()[0]
    finally:
        pool.close()
    assert versions == [1] and half is None


def test_atc_role_cannot_write_plane_tables(pg_urls, plane):
    pid = plane.project("HOME")
    with psycopg.connect(pg_urls["atc"]) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
        c.execute("UPDATE public.projects SET name = 'x' WHERE id = %s", (pid,))


def test_atc_role_can_read_plane_tables(pg_urls, plane):
    pid = plane.project("HOME", "Home")
    with psycopg.connect(pg_urls["atc"]) as c:
        assert c.execute("SELECT name FROM public.projects WHERE id = %s", (pid,)).fetchone() == ("Home",)


def test_atc_role_writes_its_own_schema(atc_conn):
    pid = "00000000-0000-0000-0000-000000000001"
    atc_conn.execute("INSERT INTO atc.project (plane_id, column_key, rank) VALUES (%s, 'next', 'V')", (pid,))
    row = atc_conn.execute("SELECT column_key, deploys, bau_enabled FROM atc.project").fetchone()
    assert row == ("next", False, False)


def test_ranks_are_byte_ordered(atc_conn):
    for i, rank in enumerate(["a", "B", "0"]):
        atc_conn.execute(
            "INSERT INTO atc.project (plane_id, column_key, rank) VALUES (%s, 'backlog', %s)",
            (f"00000000-0000-0000-0000-00000000000{i}", rank),
        )
    ranks = [r[0] for r in atc_conn.execute("SELECT rank FROM atc.project ORDER BY rank")]
    assert ranks == ["0", "B", "a"]


def test_points_must_be_positive_and_sourced(atc_conn):
    iid = "00000000-0000-0000-0000-000000000009"
    with pytest.raises(psycopg.errors.CheckViolation):
        atc_conn.execute(
            "INSERT INTO atc.work_item (plane_id, points, points_source) VALUES (%s, 0, 'martin')", (iid,)
        )
    with pytest.raises(psycopg.errors.CheckViolation):
        atc_conn.execute(
            "INSERT INTO atc.work_item (plane_id, points, points_source) VALUES (%s, 3, 'guess')", (iid,)
        )


def test_only_one_unsorted_module_per_project(atc_conn):
    sql = (
        "INSERT INTO atc.module (id, project_id, unsorted, column_key, column_rank, card_rank)"
        " VALUES (%s, '00000000-0000-0000-0000-0000000000aa', true, 'backlog', 'V', 'V')"
    )
    atc_conn.execute(sql, ("00000000-0000-0000-0000-000000000001",))
    with pytest.raises(psycopg.errors.UniqueViolation):
        atc_conn.execute(sql, ("00000000-0000-0000-0000-000000000002",))


def test_tables_are_emptied_between_tests(atc_conn, plane):
    assert atc_conn.execute("SELECT count(*) FROM atc.project").fetchone() == (0,)
    assert plane.conn.execute("SELECT count(*) FROM public.projects").fetchone() == (0,)


def test_plane_factory_builds_refs_and_memberships(plane):
    pid = plane.project("HOME")
    started = plane.state(pid, "started")
    mod = plane.module(pid, "Lights")
    first = plane.item(pid, "Fit the bulb", started, modules=[mod])
    second = plane.item(pid, "Wire the switch", started)
    assert plane.ref(first) == "HOME-1" and plane.ref(second) == "HOME-2"
    assert plane.name("HOME-2") == "Wire the switch"
    plane.remove_from_module(first, mod)
    live = plane.conn.execute("SELECT count(*) FROM public.module_issues WHERE deleted_at IS NULL").fetchone()
    assert live == (0,)
    plane.archive_project(pid)
    plane.delete_module(mod)
    assert plane.conn.execute(
        "SELECT p.archived_at IS NOT NULL, m.deleted_at IS NOT NULL FROM public.projects p"
        " JOIN public.modules m ON m.project_id = p.id"
    ).fetchone() == (True, True)
    with pytest.raises(KeyError):
        plane.name("HOME-99")


def test_health_is_served(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200 and resp.json()["ok"] is True


def test_health_is_503_when_the_database_is_unreachable(client):
    client.app.state.pool.close()
    resp = client.get("/api/health")
    assert resp.status_code == 503 and resp.json()["ok"] is False


def test_duplicate_migration_versions_are_refused(tmp_path):
    (tmp_path / "001_a.sql").write_text("SELECT 1")
    (tmp_path / "001_b.sql").write_text("SELECT 1")
    (tmp_path / "README").write_text("not a migration")
    with pytest.raises(ValueError, match="duplicate"):
        db.migrations(tmp_path)


def test_settings_require_database_url(monkeypatch):
    monkeypatch.delenv("ATC_DATABASE_URL", raising=False)
    with pytest.raises(KeyError):
        Settings.from_env()


def test_settings_read_the_environment(monkeypatch):
    monkeypatch.setenv("ATC_DATABASE_URL", "postgresql://atc@db/plane")
    monkeypatch.setenv("ATC_WORKSPACE_SLUG", "other")
    monkeypatch.setenv("ATC_MAX_POINTS", "40")
    monkeypatch.setenv("ATC_RECONCILE_SECONDS", "0")
    monkeypatch.setenv("ATC_PLANE_WEB_URL", "https://plane.example")
    monkeypatch.setenv("ATC_STATIC_DIR", "/app/static")
    assert Settings.from_env() == Settings(
        database_url="postgresql://atc@db/plane",
        workspace_slug="other",
        max_points=40,
        reconcile_seconds=0,
        plane_web_url="https://plane.example",
        static_dir=Path("/app/static"),
    )


def test_settings_defaults(monkeypatch):
    for name in ("ATC_WORKSPACE_SLUG", "ATC_MAX_POINTS", "ATC_RECONCILE_SECONDS", "ATC_PLANE_WEB_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("ATC_STATIC_DIR", raising=False)
    monkeypatch.setenv("ATC_DATABASE_URL", "postgresql://atc@db/plane")
    s = Settings.from_env()
    assert (s.workspace_slug, s.max_points, s.reconcile_seconds) == ("nakomis", 100, 300)
    assert s.plane_web_url == "https://plane.home.nakomis.com" and s.static_dir is None


def test_static_dir_serves_the_web_app_after_the_api(pg_urls, tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><title>ATC</title>")
    (tmp_path / "app.js").write_text("console.log('atc')")
    app = create_app(Settings(database_url=pg_urls["atc"], reconcile_seconds=0, static_dir=tmp_path))
    with TestClient(app) as c:
        index = c.get("/")
        assert index.status_code == 200 and "<title>ATC</title>" in index.text
        assert c.get("/app.js").text == "console.log('atc')"
        assert c.get("/api/health").json()["ok"] is True  # the API still wins over the mount


def test_no_static_dir_serves_nothing_at_root(client):
    assert client.get("/").status_code == 404
