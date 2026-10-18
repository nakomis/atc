from datetime import UTC, datetime, timedelta

import psycopg
from helpers import move


def test_next_prefers_in_progress_then_up_next(client, plane):
    a, b = plane.project("AAA"), plane.project("BBB")
    plane.item(a, "a1", plane.state(a, "unstarted"))
    plane.item(b, "b1", plane.state(b, "unstarted"))
    assert client.get("/api/next").json() == {"column": None, "next": None, "runners_up": []}
    move(client, "project", b, "next")
    assert client.get("/api/next").json()["next"]["ref"] == "BBB-1"
    move(client, "project", a, "in_progress")
    r = client.get("/api/next").json()
    assert (r["column"], r["next"]["ref"], r["next"]["project"]["identifier"]) == (
        "in_progress",
        "AAA-1",
        "AAA",
    )


def test_runners_up_follow_sort_order(client, plane):
    p = plane.project("HOME")
    s = plane.state(p, "unstarted")
    for n, so in (("third", 3.0), ("first", 1.0), ("second", 2.0), ("fourth", 4.0)):
        plane.item(p, n, s, sort_order=so)
    move(client, "project", p, "in_progress")
    r = client.get("/api/next").json()
    assert [r["next"]["name"]] + [x["name"] for x in r["runners_up"]] == ["first", "second", "third"]


def test_runners_up_cross_modules_but_not_columns(client, plane):
    a, b = plane.project("AAA"), plane.project("BBB")
    s = plane.state(a, "unstarted")
    m = plane.module(a, "M")
    plane.item(a, "in module", s, modules=[m])
    plane.item(a, "loose", s)
    t = plane.state(b, "unstarted")
    plane.item(b, "other column", t)
    move(client, "project", a, "in_progress")
    move(client, "project", b, "next")
    r = client.get("/api/next").json()
    assert [r["next"]["name"]] + [x["name"] for x in r["runners_up"]] == ["in module", "loose"]
    assert r["next"]["module"]["name"] == "M" and r["next"]["module"]["unsorted"] is False
    assert r["runners_up"][0]["module"]["unsorted"] is True


def test_sort_order_ties_break_by_priority_then_created(client, plane):  # Review Focus 2
    t0 = datetime(2026, 10, 1, tzinfo=UTC)
    p = plane.project("HOME")
    s = plane.state(p, "unstarted")
    plane.item(p, "old low", s, priority="low", created_at=t0)
    plane.item(p, "new urgent", s, priority="urgent", created_at=t0 + timedelta(days=1))
    plane.item(p, "older none", s, priority="none", created_at=t0 - timedelta(days=1))
    plane.item(p, "newer low", s, priority="low", created_at=t0 + timedelta(days=2))
    refs = client.get("/api/priority").json()["refs"]
    assert [plane.name(r) for r in refs] == ["new urgent", "old low", "newer low", "older none"]


def test_priority_walks_in_progress_up_next_backlog(client, plane):
    a, b, c = (plane.project(x) for x in ("AAA", "BBB", "CCC"))
    for p in (a, b, c):
        plane.item(p, "x", plane.state(p, "unstarted"))
    move(client, "project", c, "in_progress")
    move(client, "project", b, "next")
    assert client.get("/api/priority").json()["refs"] == ["CCC-1", "BBB-1", "AAA-1"]


def seed_project(pg_urls, plane_id, repo, **extra):
    deploys = extra.get("deploys", False)
    action = extra.get("deploy_action", "")
    with psycopg.connect(pg_urls["admin"], autocommit=True) as conn:
        conn.execute(
            "INSERT INTO atc.project (plane_id, column_key, rank, repo, deploys, deploy_action, bau_enabled)"
            " VALUES (%s, 'backlog', 'n', %s, %s, %s, true)"
            " ON CONFLICT (plane_id) DO UPDATE SET repo = excluded.repo, deploys = excluded.deploys,"
            " deploy_action = excluded.deploy_action, bau_enabled = true",
            (plane_id, repo, deploys, action),
        )


def test_bau_projects_in_board_order_with_metadata(client, plane, pg_urls):
    a, b, c = plane.project("AAA"), plane.project("BBB"), plane.project("CCC")
    for p in (a, b):
        plane.item(p, "x", plane.state(p, "unstarted"))
    seed_project(pg_urls, a, "nakomis/aaa")
    seed_project(pg_urls, b, "nakomis/bbb", deploys=True, deploy_action="Approve it")
    move(client, "project", b, "in_progress")
    got = client.get("/api/projects?bau_enabled=true").json()
    assert [(p["identifier"], p["repo"], p["deploys"]) for p in got] == [
        ("BBB", "nakomis/bbb", True),
        ("AAA", "nakomis/aaa", False),
    ]
    assert got[0]["deploy_action"] == "Approve it" and got[0]["column"] == "in_progress"
    # Unfiltered, a project with no open items is appended after the board's, by identifier.
    allp = client.get("/api/projects").json()
    assert [p["identifier"] for p in allp] == ["BBB", "AAA", "CCC"]
    assert allp[2]["repo"] is None and allp[2]["bau_enabled"] is False and allp[2]["column"] == "backlog"
