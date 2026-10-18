from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
from helpers import col, cols

from atc import plane as plane_reader
from atc.board import unsorted_id


def atc_sql(pg_urls, sql, params=()):
    """Write ATC rows directly, as the atc role (moves land in Task 5)."""
    with psycopg.connect(pg_urls["atc"], autocommit=True) as conn:
        conn.execute(sql, params)


def project_row(pg_urls, pid, column, rank, hidden=False):
    atc_sql(
        pg_urls,
        "INSERT INTO atc.project (plane_id, column_key, rank, hidden_at)"
        " VALUES (%s, %s, %s, CASE WHEN %s THEN now() END)",
        (pid, column, rank, hidden),
    )


def module_row(pg_urls, mid, pid, column, column_rank="V", card_rank="V", unsorted=False):
    atc_sql(
        pg_urls,
        "INSERT INTO atc.module (id, project_id, unsorted, column_key, column_rank, card_rank)"
        " VALUES (%s, %s, %s, %s, %s, %s)",
        (mid, pid, unsorted, column, column_rank, card_rank),
    )


def points(pg_urls, item_id, n, source="martin"):
    atc_sql(
        pg_urls,
        "INSERT INTO atc.work_item (plane_id, points, points_source) VALUES (%s, %s, %s)",
        (item_id, n, source),
    )


# --- The brief's tests -------------------------------------------------------------------


def test_rowless_projects_land_in_backlog_with_unsorted(client, plane):
    p = plane.project("HOME")
    s = plane.state(p, "unstarted")
    plane.item(p, "loose", s)
    c = cols(client)
    [card] = c["backlog"]["cards"]
    assert (card["kind"], card["identifier"]) == ("project", "HOME")
    assert [m["unsorted"] for m in card["modules"]] == [True]
    assert c["next"]["cards"] == [] and c["in_progress"]["cards"] == []


def test_closed_items_and_closed_modules_are_not_counted(client, plane):
    p = plane.project("HOME")
    open_ = plane.state(p, "started")
    done = plane.state(p, "completed")
    m = plane.module(p, "Done module", status="completed")
    plane.item(p, "finished", done)
    plane.item(p, "in closed module", open_, modules=[m])
    card = cols(client)["backlog"]["cards"][0]
    assert [x["name"] for x in card["modules"]] == ["Unsorted"]
    assert [i["name"] for i in card["modules"][0]["items"]] == ["in closed module"]


def test_item_in_two_modules_counts_once(client, plane):  # Review Focus 1
    p = plane.project("HOME")
    s = plane.state(p, "unstarted")
    a, b = plane.module(p, "A"), plane.module(p, "B")
    plane.item(p, "shared", s, modules=[a, b])
    board = client.get("/api/board").json()
    seen = [
        i["ref"]
        for col_ in board["columns"]
        for card in col_["cards"]
        for m in card["modules"]
        for i in m["items"]
    ]
    assert seen == ["HOME-1"]
    assert sum(col_["unestimated"] for col_ in board["columns"]) == 1


def test_soft_deleted_membership_is_ignored(client, plane):  # Review Focus 4
    p = plane.project("HOME")
    s = plane.state(p, "unstarted")
    m = plane.module(p, "M")
    i = plane.item(p, "moved out", s, modules=[m])
    plane.remove_from_module(i, m)
    card = cols(client)["backlog"]["cards"][0]
    assert [x["name"] for x in card["modules"]] == ["Unsorted"]


def test_archived_project_is_absent(client, plane):
    p = plane.project("OLD", archived=True)
    plane.item(p, "x", plane.state(p, "unstarted"))
    assert all(col_["cards"] == [] for col_ in client.get("/api/board").json()["columns"])


def test_triage_items_count_as_open(client, plane):
    p = plane.project("HOME")
    plane.item(p, "new", plane.state(p, "triage"))
    assert cols(client)["backlog"]["unestimated"] == 1


def test_all_true_includes_collapsed(client, plane):
    p = plane.project("HOME")
    plane.module(p, "Empty done", status="completed")
    assert client.get("/api/board").json()["columns"][0]["cards"] == []
    assert client.get("/api/board?all=true").json()["columns"][0]["cards"]


def test_item_links_point_at_plane(client, plane):
    p = plane.project("HOME")
    plane.item(p, "x", plane.state(p, "unstarted"))
    item = cols(client)["backlog"]["cards"][0]["modules"][0]["items"][0]
    assert item["url"] == "https://plane.home.nakomis.com/nakomis/browse/HOME-1/"


# --- Further cover -----------------------------------------------------------------------


def test_board_shape_follows_the_contract(client, plane):
    p = plane.project("HOME", name="Home infra")
    s = plane.state(p, "unstarted", name="Todo")
    m = plane.module(p, "Lights", status="in-progress")
    i = plane.item(p, "bulb", s, modules=[m], priority="high")
    body = client.get("/api/board").json()
    assert set(body) == {"columns", "max_points", "generated_at"}
    assert body["max_points"] == 100
    datetime.fromisoformat(body["generated_at"])
    assert [(c["key"], c["label"]) for c in body["columns"]] == [
        ("backlog", "Backlog"),
        ("next", "Up next"),
        ("in_progress", "In progress"),
    ]
    card = col(body, "backlog")["cards"][0]
    assert {k: card[k] for k in ("kind", "id", "project_id", "identifier", "label")} == {
        "kind": "project",
        "id": str(p),
        "project_id": str(p),
        "identifier": "HOME",
        "label": "Home infra",
    }
    lights = card["modules"][0]
    assert {k: lights[k] for k in ("id", "name", "unsorted", "status", "points", "unestimated")} == {
        "id": str(m),
        "name": "Lights",
        "unsorted": False,
        "status": "in-progress",
        "points": 0,
        "unestimated": 1,
    }
    assert lights["items"] == [
        {
            "id": str(i),
            "ref": "HOME-1",
            "name": "bulb",
            "state": "Todo",
            "state_group": "unstarted",
            "priority": "high",
            "points": None,
            "points_source": None,
            "url": "https://plane.home.nakomis.com/nakomis/browse/HOME-1/",
        }
    ]


def test_module_in_another_column_is_a_module_card(client, plane, pg_urls):
    p = plane.project("HOME")
    s = plane.state(p, "unstarted")
    m = plane.module(p, "Lights")
    plane.item(p, "bulb", s, modules=[m])
    plane.item(p, "loose", s)
    module_row(pg_urls, m, p, "in_progress")
    c = cols(client)
    [card] = c["in_progress"]["cards"]
    assert (card["kind"], card["id"], card["project_id"], card["label"]) == (
        "module",
        str(m),
        str(p),
        "HOME · Lights",
    )
    assert [x["name"] for x in card["modules"]] == ["Lights"]
    [home] = c["backlog"]["cards"]
    assert [x["name"] for x in home["modules"]] == ["Unsorted"]


def test_project_card_shows_when_all_its_modules_are_elsewhere(client, plane, pg_urls):
    p = plane.project("HOME")
    s = plane.state(p, "unstarted")
    m = plane.module(p, "Lights")
    plane.item(p, "bulb", s, modules=[m])
    project_row(pg_urls, p, "next", "V")
    module_row(pg_urls, m, p, "in_progress")
    c = cols(client)
    [card] = c["next"]["cards"]
    assert (card["kind"], card["modules"], card["points"], card["unestimated"]) == ("project", [], 0, 0)
    assert c["in_progress"]["cards"][0]["label"] == "HOME · Lights"
    assert c["backlog"]["cards"] == []


def test_rowless_unsorted_follows_its_project(client, plane, pg_urls):
    p = plane.project("HOME")
    plane.item(p, "loose", plane.state(p, "unstarted"))
    project_row(pg_urls, p, "in_progress", "V")
    c = cols(client)
    [card] = c["in_progress"]["cards"]
    assert [m["unsorted"] for m in card["modules"]] == [True]
    assert card["modules"][0]["id"] == str(unsorted_id(p))


def test_unsorted_row_places_it(client, plane, pg_urls):
    p = plane.project("HOME")
    plane.item(p, "loose", plane.state(p, "unstarted"))
    module_row(pg_urls, unsorted_id(p), p, "next", unsorted=True)
    [card] = cols(client)["next"]["cards"]
    assert (card["kind"], card["label"]) == ("module", "HOME · Unsorted")
    assert card["modules"][0]["status"] is None


def test_cards_sort_by_shared_rank_then_rowless_by_created(client, plane, pg_urls):
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    ids = {}
    for ident in ("AAA", "BBB", "CCC", "DDD"):
        ids[ident] = plane.project(ident)
        plane.item(ids[ident], "x", plane.state(ids[ident], "unstarted"))
    for n, ident in enumerate(("DDD", "CCC")):  # rowless; CCC created later
        plane.conn.execute(
            "UPDATE public.projects SET created_at = %s WHERE id = %s", (t0 + timedelta(days=n), ids[ident])
        )
    project_row(pg_urls, ids["AAA"], "backlog", "k")
    project_row(pg_urls, ids["BBB"], "backlog", "B")  # "B" < "k" bytewise
    other = plane.project("EEE")
    m = plane.module(other, "Mod")
    plane.item(other, "y", plane.state(other, "unstarted"), modules=[m])
    project_row(pg_urls, other, "next", "V")
    module_row(pg_urls, m, other, "backlog", column_rank="a")  # between B and k
    labels = [c["label"] for c in cols(client)["backlog"]["cards"]]
    assert labels == ["BBB project", "EEE · Mod", "AAA project", "DDD project", "CCC project"]


def test_project_card_modules_follow_card_rank(client, plane, pg_urls):
    p = plane.project("HOME")
    s = plane.state(p, "unstarted")
    m1, m2, m3 = (plane.module(p, n) for n in ("M1", "M2", "M3"))
    for m in (m1, m2, m3):
        plane.item(p, "x", s, modules=[m])
    plane.item(p, "loose", s)
    module_row(pg_urls, m2, p, "backlog", card_rank="a")
    module_row(pg_urls, m3, p, "backlog", card_rank="Z")
    names = [m["name"] for m in cols(client)["backlog"]["cards"][0]["modules"]]
    assert names == ["M3", "M2", "M1", "Unsorted"]


def test_hidden_rows_count_as_rowless(client, plane, pg_urls):
    p = plane.project("HOME")
    plane.item(p, "x", plane.state(p, "unstarted"))
    project_row(pg_urls, p, "in_progress", "V", hidden=True)
    c = cols(client)
    assert [x["identifier"] for x in c["backlog"]["cards"]] == ["HOME"]
    assert c["in_progress"]["cards"] == []


def test_item_goes_to_first_open_module_in_priority_order(client, plane, pg_urls):
    p = plane.project("HOME")
    s = plane.state(p, "unstarted")
    late, early, closed = (
        plane.module(p, "Late"),
        plane.module(p, "Early"),
        plane.module(p, "Shut", "completed"),
    )
    plane.item(p, "shared", s, modules=[late, early, closed])
    plane.item(p, "only late", s, modules=[late])
    module_row(pg_urls, early, p, "in_progress")  # In progress has the highest priority
    module_row(pg_urls, closed, p, "in_progress", column_rank="A")
    c = cols(client)
    [early_card] = c["in_progress"]["cards"]  # Shut collapses
    assert [i["name"] for i in early_card["modules"][0]["items"]] == ["shared"]
    home = c["backlog"]["cards"][0]
    assert [(m["name"], [i["name"] for i in m["items"]]) for m in home["modules"]] == [
        ("Late", ["only late"])
    ]


def test_items_order_by_sort_order_then_priority_created_sequence(client, plane):
    t0 = datetime(2026, 10, 1, tzinfo=UTC)
    p = plane.project("HOME")
    s = plane.state(p, "unstarted")
    plane.item(p, "last", s, sort_order=9.0)
    plane.item(p, "low old", s, sort_order=1.0, priority="low", created_at=t0)
    plane.item(p, "urgent new", s, sort_order=1.0, priority="urgent", created_at=t0 + timedelta(days=1))
    plane.item(p, "low older", s, sort_order=1.0, priority="low", created_at=t0 - timedelta(days=1))
    plane.item(p, "none same", s, sort_order=1.0, priority="none", created_at=t0)
    plane.item(p, "none same 2", s, sort_order=1.0, priority="none", created_at=t0)
    items = cols(client)["backlog"]["cards"][0]["modules"][0]["items"]
    assert [i["name"] for i in items] == [
        "urgent new",
        "low older",
        "low old",
        "none same",
        "none same 2",
        "last",
    ]


def test_points_sum_through_modules_cards_and_columns(client, plane, pg_urls):
    p = plane.project("HOME")
    s = plane.state(p, "unstarted")
    m = plane.module(p, "M")
    a = plane.item(p, "a", s, modules=[m])
    b = plane.item(p, "b", s, modules=[m])
    plane.item(p, "c", s, modules=[m])
    d = plane.item(p, "d", s)
    for item, n in ((a, 3), (b, 5), (d, 8)):
        points(pg_urls, item, n)
    module_row(pg_urls, m, p, "next")
    c = cols(client)
    mod = c["next"]["cards"][0]["modules"][0]
    assert (mod["points"], mod["unestimated"]) == (8, 1)
    assert (c["next"]["points"], c["next"]["unestimated"]) == (8, 1)
    home = c["backlog"]["cards"][0]
    assert (home["points"], home["unestimated"], c["backlog"]["points"]) == (8, 0, 8)
    item_d = home["modules"][0]["items"][0]
    assert (item_d["points"], item_d["points_source"]) == (8, "martin")


def test_collapsing_rules(client, plane, pg_urls):
    busy = plane.project("BUSY")
    s = plane.state(busy, "unstarted")
    plane.module(busy, "Cancelled", status="cancelled")
    plane.module(busy, "Planned but empty")
    empty_open = plane.module(busy, "Open mod")
    plane.item(busy, "x", s, modules=[empty_open])
    idle = plane.project("IDLE")
    idle_mod = plane.module(idle, "Idle mod")
    module_row(pg_urls, idle_mod, idle, "next")
    c = cols(client)
    [card] = c["backlog"]["cards"]
    # No empty Unsorted, no empty or cancelled module.
    assert [m["name"] for m in card["modules"]] == ["Open mod"]
    assert c["next"]["cards"] == []  # IDLE has no open items: its module card goes too
    everything = {c_["key"]: c_ for c_ in client.get("/api/board?all=true").json()["columns"]}
    assert [x["identifier"] for x in everything["backlog"]["cards"]] == ["BUSY", "IDLE"]
    assert [m["name"] for m in everything["backlog"]["cards"][0]["modules"]] == [
        "Cancelled",
        "Planned but empty",
        "Open mod",
        "Unsorted",
    ]
    assert [m["name"] for m in everything["next"]["cards"][0]["modules"]] == ["Idle mod"]


def test_other_workspaces_deleted_rows_and_drafts_are_ignored(client, plane):
    p = plane.project("HOME")
    s = plane.state(p, "unstarted")
    keep = plane.item(p, "keep", s)
    gone = plane.item(p, "deleted", s)
    draft = plane.item(p, "draft", s)
    archived = plane.item(p, "archived", s)
    plane.conn.execute("UPDATE public.issues SET deleted_at = now() WHERE id = %s", (gone,))
    plane.conn.execute("UPDATE public.issues SET is_draft = true WHERE id = %s", (draft,))
    plane.conn.execute("UPDATE public.issues SET archived_at = current_date WHERE id = %s", (archived,))
    dead = plane.module(p, "Dead")
    plane.item(p, "in dead module", s, modules=[dead])
    plane.delete_module(dead)
    elsewhere = plane.workspace("other")
    other = uuid4()
    plane.conn.execute(
        "INSERT INTO public.projects (id, workspace_id, identifier, name) VALUES (%s, %s, 'OTH', 'Other')",
        (other, elsewhere),
    )
    plane.item(other, "theirs", plane.state(other, "unstarted"))
    gone_project = plane.project("GONE")
    plane.item(gone_project, "x", plane.state(gone_project, "unstarted"))
    plane.conn.execute("UPDATE public.projects SET deleted_at = now() WHERE id = %s", (gone_project,))
    c = cols(client)
    [card] = c["backlog"]["cards"]
    assert card["identifier"] == "HOME"
    assert [m["name"] for m in card["modules"]] == ["Unsorted"]
    assert [i["id"] for i in card["modules"][0]["items"][:1]] == [str(keep)]
    assert [i["name"] for i in card["modules"][0]["items"]] == ["keep", "in dead module"]


def test_unsorted_id_is_stable():
    pid = uuid4()
    assert unsorted_id(pid) == unsorted_id(pid) != unsorted_id(uuid4())


def test_read_plane_snapshot(atc_conn, plane):
    p = plane.project("HOME")
    s = plane.state(p, "started")
    done = plane.module(p, "Done", status="completed")
    m = plane.module(p, "M")
    i = plane.item(p, "x", s, modules=[m, done])
    plane.item(p, "closed", plane.state(p, "cancelled"))
    snap = plane_reader.read_plane(atc_conn, "nakomis")
    assert [x.identifier for x in snap.projects] == ["HOME"]
    assert {x.name: x.status for x in snap.modules} == {"Done": "completed", "M": "planned"}
    [item] = snap.items
    assert (item.id, item.ref, item.state_group, set(item.module_ids)) == (i, "HOME-1", "started", {m, done})
    assert plane_reader.read_plane(atc_conn, "nobody").projects == []


def test_missing_columns_none_when_granted(atc_conn):
    assert plane_reader.missing_columns(atc_conn) == []


def test_missing_columns_reports_unreadable_tables(fresh_db):
    with psycopg.connect(fresh_db["admin"], autocommit=True) as conn:
        conn.execute("REVOKE SELECT ON public.module_issues FROM atc")
        conn.execute('ALTER TABLE public.states RENAME COLUMN "group" TO state_group')
    with psycopg.connect(fresh_db["atc"]) as conn:
        missing = plane_reader.missing_columns(conn)
    expected = {f"module_issues.{c}" for c in plane_reader.REQUIRED_COLUMNS["module_issues"]}
    assert set(missing) == expected | {"states.group"}
    assert missing == sorted(missing)
