import threading
import time

import psycopg
import pytest
from fastapi.testclient import TestClient
from helpers import col, move

from atc import ranks
from atc import reconcile as reconcile_module
from atc.app import MOVE_LOCK_KEY, create_app
from atc.board import unsorted_id
from atc.reconcile import reconcile
from atc.settings import Settings


def test_reconcile_creates_rows_and_is_idempotent(atc_conn, plane):
    plane.project("HOME")
    plane.module(plane.project("BAU"), "Cabal")
    r1 = reconcile(atc_conn, "nakomis")
    r2 = reconcile(atc_conn, "nakomis")
    assert (r1.created_projects, r1.created_modules) == (2, 3)  # 2 Unsorted + Cabal
    assert (r2.created_projects, r2.created_modules) == (0, 0)
    assert r1.missing == [] and r1.at.tzinfo is not None


def test_new_rows_sit_at_the_bottom_of_backlog_in_creation_order(atc_conn, plane):
    a, b = plane.project("AAA"), plane.project("BBB")
    reconcile(atc_conn, "nakomis")
    rows = dict(atc_conn.execute("SELECT plane_id, rank FROM atc.project").fetchall())
    assert rows[a] < rows[b]
    assert {r[0] for r in atc_conn.execute("SELECT column_key FROM atc.project")} == {"backlog"}
    assert {r[0] for r in atc_conn.execute("SELECT column_key FROM atc.module")} == {"backlog"}


def test_reconcile_rebalances_a_long_backlog_tail(atc_conn, plane):  # final review I2
    old = plane.project("OLD")
    reconcile(atc_conn, "nakomis")
    atc_conn.execute("UPDATE atc.project SET rank = %s WHERE plane_id = %s", ("z" * 500 + "1", old))
    atc_conn.execute("UPDATE atc.module SET column_rank = %s", ("z" * 499 + "1",))
    new = [plane.project(f"N{n:02}") for n in range(3)]
    assert reconcile(atc_conn, "nakomis").created_projects == 3
    rows = dict(atc_conn.execute("SELECT plane_id, rank FROM atc.project").fetchall())
    module_ranks = [r for (r,) in atc_conn.execute("SELECT column_rank FROM atc.module")]
    assert [rows[p] for p in [old, *new]] == sorted(rows[p] for p in [old, *new])
    assert max(map(len, [*rows.values(), *module_ranks])) <= ranks.REBALANCE_LENGTH


def test_new_module_of_a_moved_project_is_a_backlog_card(client, plane, atc_conn):
    p = plane.project("HOME")
    plane.item(p, "x", plane.state(p, "unstarted"))
    reconcile(atc_conn, "nakomis")
    move(client, "project", p, "in_progress")
    m = plane.module(p, "Late")
    plane.item(p, "y", plane.state(p, "unstarted"), modules=[m])
    assert reconcile(atc_conn, "nakomis").created_modules == 1
    board = client.get("/api/board").json()
    assert [c["id"] for c in col(board, "backlog")["cards"]] == [str(m)]
    assert col(board, "in_progress")["cards"][0]["id"] == str(p)


def test_unsorted_of_an_existing_project_row_takes_the_project_column(client, plane, atc_conn):
    p = plane.project("HOME")
    plane.item(p, "x", plane.state(p, "unstarted"))
    move(client, "project", p, "next")
    atc_conn.execute("DELETE FROM atc.module")  # the project row exists; its Unsorted row does not
    assert reconcile(atc_conn, "nakomis").created_modules == 1
    assert atc_conn.execute(
        "SELECT column_key FROM atc.module WHERE id = %s", (unsorted_id(p),)
    ).fetchone() == ("next",)


def test_reconcile_hides_archived_project_and_unhides_on_return(atc_conn, plane, pg_urls):  # RF 4
    p = plane.project("HOME")
    reconcile(atc_conn, "nakomis")
    plane.archive_project(p)
    assert reconcile(atc_conn, "nakomis").hidden == 2  # the project and its Unsorted row
    assert reconcile(atc_conn, "nakomis").hidden == 0
    assert atc_conn.execute("SELECT count(*) FROM atc.project WHERE hidden_at IS NOT NULL").fetchone() == (1,)
    plane.unarchive_project(p)
    r = reconcile(atc_conn, "nakomis")
    assert (r.unhidden, r.created_projects, r.created_modules) == (2, 0, 0)
    assert atc_conn.execute("SELECT count(*) FROM atc.project WHERE hidden_at IS NOT NULL").fetchone() == (0,)


def test_deleted_module_is_hidden_and_nothing_is_deleted(atc_conn, plane):
    p = plane.project("HOME")
    m = plane.module(p, "Cabal")
    item = plane.item(p, "x", plane.state(p, "unstarted"), modules=[m])
    atc_conn.execute(
        "INSERT INTO atc.work_item (plane_id, points, points_source) VALUES (%s, 2, 'martin')", (item,)
    )
    reconcile(atc_conn, "nakomis")
    plane.delete_module(m)
    assert reconcile(atc_conn, "nakomis").hidden == 1
    assert atc_conn.execute("SELECT count(*) FROM atc.module").fetchone() == (2,)
    assert atc_conn.execute("SELECT count(*) FROM atc.work_item").fetchone() == (1,)


def test_reconcile_does_not_move_existing_rows(client, plane, atc_conn):
    p = plane.project("HOME")
    plane.item(p, "x", plane.state(p, "unstarted"))
    move(client, "project", p, "in_progress")
    reconcile(atc_conn, "nakomis")
    assert col(client.get("/api/board").json(), "in_progress")["cards"][0]["identifier"] == "HOME"


def test_unknown_workspace_raises_rather_than_hiding_everything(atc_conn, plane):
    plane.project("HOME")
    reconcile(atc_conn, "nakomis")
    with pytest.raises(LookupError):
        reconcile(atc_conn, "nowhere")
    assert atc_conn.execute("SELECT count(*) FROM atc.project WHERE hidden_at IS NOT NULL").fetchone() == (0,)


def test_hide_waits_for_the_move_lock(atc_conn, plane, pg_urls):
    p = plane.project("HOME")
    reconcile(atc_conn, "nakomis")
    plane.archive_project(p)
    done = threading.Event()
    with psycopg.connect(pg_urls["atc"]) as holder:
        holder.execute("SELECT pg_advisory_xact_lock(%s)", (MOVE_LOCK_KEY,))
        t = threading.Thread(target=lambda: (reconcile(atc_conn, "nakomis"), done.set()))
        t.start()
        assert not done.wait(0.5)
        holder.commit()
    t.join(10)
    assert done.is_set()


def test_missing_column_is_reported_and_health_fails(client, atc_conn, pg_urls):
    with psycopg.connect(pg_urls["admin"], autocommit=True) as admin:
        admin.execute("REVOKE SELECT ON public.module_issues FROM atc")
        try:
            r = reconcile(atc_conn, "nakomis")
            assert "module_issues.issue_id" in r.missing
            assert (r.created_projects, r.created_modules, r.hidden, r.unhidden) == (0, 0, 0, 0)
            resp = client.get("/api/health")
            assert resp.status_code == 503
            assert "module_issues.issue_id" in resp.json()["missing"] and resp.json()["ok"] is False
        finally:
            admin.execute("GRANT SELECT ON public.module_issues TO atc")
    assert client.get("/api/health").status_code == 200


def test_health_reports_hidden_counts_and_last_reconcile(client, plane, atc_conn):
    p = plane.project("HOME")
    body = client.get("/api/health").json()
    assert body == {
        "ok": True,
        "missing": [],
        "last_reconcile": None,
        "hidden": {"projects": 0, "modules": 0},
    }
    reconcile(atc_conn, "nakomis")
    plane.archive_project(p)
    reconcile(atc_conn, "nakomis")
    assert client.get("/api/health").json()["hidden"] == {"projects": 1, "modules": 1}


def test_loop_runs_at_start_up_and_records_last_reconcile(pg_urls, plane):
    plane.project("HOME")
    app = create_app(Settings(database_url=pg_urls["atc"], reconcile_seconds=3600))
    with TestClient(app) as c:
        for _ in range(100):
            body = c.get("/api/health").json()
            if body["last_reconcile"]:
                break
            time.sleep(0.1)
        assert body["ok"] is True and body["last_reconcile"]


def test_failed_reconcile_is_recorded_not_fatal(pg_urls, plane, monkeypatch):
    def boom(conn, slug):
        raise RuntimeError("plane unreachable")

    monkeypatch.setattr(reconcile_module, "reconcile", boom)
    app = create_app(Settings(database_url=pg_urls["atc"], reconcile_seconds=3600))
    with TestClient(app) as c:
        for _ in range(100):
            resp = c.get("/api/health")
            if resp.status_code == 503:
                break
            time.sleep(0.1)
        assert resp.status_code == 503 and resp.json()["missing"] == []
        assert c.get("/api/board").status_code == 200


def test_reconcile_snapshot_follows_the_lock_so_a_waiting_pass_does_not_conflict(atc_conn, plane, pg_urls):
    # Final review I3: the snapshot used to be taken before the wait, so a write committed while
    # reconcile waited made its hide fail with "could not serialize access".
    p = plane.project("HOME")
    reconcile(atc_conn, "nakomis")
    plane.archive_project(p)
    outcome: list = []

    def run():
        try:
            outcome.append(reconcile(atc_conn, "nakomis"))
        except Exception as e:  # noqa: BLE001 - reported by the assertion below
            outcome.append(e)

    with psycopg.connect(pg_urls["atc"]) as holder:
        holder.execute("SELECT pg_advisory_xact_lock(%s)", (MOVE_LOCK_KEY,))
        t = threading.Thread(target=run)
        t.start()
        time.sleep(0.5)  # reconcile is now waiting for the lock
        holder.execute("UPDATE atc.project SET updated_at = now() WHERE plane_id = %s", (p,))
        holder.commit()
    t.join(10)
    assert len(outcome) == 1 and not isinstance(outcome[0], Exception), outcome
    assert outcome[0].hidden == 2  # the project and its Unsorted group
    with psycopg.connect(pg_urls["atc"]) as c:  # and the session lock was released
        assert c.execute("SELECT pg_try_advisory_lock(%s)", (MOVE_LOCK_KEY,)).fetchone() == (True,)


def _serialisation_failure() -> psycopg.errors.SerializationFailure:
    return psycopg.errors.SerializationFailure("could not serialize access due to concurrent update")


def test_a_retried_serialisation_conflict_keeps_health_green(pg_urls, plane, monkeypatch):
    plane.project("HOME")
    real = reconcile_module.reconcile
    calls = []

    def flaky(conn, slug):
        calls.append(slug)
        if len(calls) == 1:
            raise _serialisation_failure()
        return real(conn, slug)

    monkeypatch.setattr(reconcile_module, "reconcile", flaky)
    app = create_app(Settings(database_url=pg_urls["atc"], reconcile_seconds=3600))
    with TestClient(app) as c:
        for _ in range(100):
            body = c.get("/api/health").json()
            if body["last_reconcile"]:
                break
            time.sleep(0.1)
        assert body["ok"] is True and body["last_reconcile"] and len(calls) == 2


def test_persistent_serialisation_conflicts_do_not_mark_health_503(pg_urls, plane, monkeypatch):
    calls = []

    def always(conn, slug):
        calls.append(slug)
        raise _serialisation_failure()

    monkeypatch.setattr(reconcile_module, "reconcile", always)
    app = create_app(Settings(database_url=pg_urls["atc"], reconcile_seconds=3600))
    with TestClient(app) as c:
        for _ in range(100):
            if len(calls) >= 3:
                break
            time.sleep(0.1)
        time.sleep(0.1)
        resp = c.get("/api/health")
        assert len(calls) == 3 and resp.status_code == 200 and resp.json()["last_reconcile"] is None
