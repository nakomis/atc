from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from helpers import cols, move

from atc.app import create_app
from atc.settings import Settings


def test_points_round_trip_and_board_totals(client, plane):
    p = plane.project("HOME")
    i = plane.item(p, "x", plane.state(p, "unstarted"))
    assert client.get(f"/api/work-items/{i}/points").json()["points"] is None
    r = client.put(f"/api/work-items/{i}/points", json={"points": 3, "source": "martin"})
    assert (r.status_code, r.json()["points"], r.json()["points_source"]) == (200, 3, "martin")
    col = client.get("/api/board").json()["columns"][0]
    assert (col["points"], col["unestimated"]) == (3, 0)


@pytest.mark.parametrize(
    "body",
    [
        {"points": 0, "source": "martin"},
        {"points": 101, "source": "martin"},
        {"points": 2, "source": "guess"},
        {"points": 2.5, "source": "mcp"},
        {"points": True, "source": "mcp"},
        {"points": "3", "source": "mcp"},
        {"source": "mcp"},
    ],
)
def test_points_validation(client, plane, body):
    p = plane.project("HOME")
    i = plane.item(p, "x", plane.state(p, "unstarted"))
    assert client.put(f"/api/work-items/{i}/points", json=body).status_code == 422


def test_points_bounds_are_inclusive_and_max_is_configurable(pg_urls, plane):
    p = plane.project("HOME")
    i = plane.item(p, "x", plane.state(p, "unstarted"))
    app = create_app(Settings(database_url=pg_urls["atc"], reconcile_seconds=0, max_points=7))
    with TestClient(app) as c:
        assert c.put(f"/api/work-items/{i}/points", json={"points": 7, "source": "mcp"}).status_code == 200
        assert c.put(f"/api/work-items/{i}/points", json={"points": 8, "source": "mcp"}).status_code == 422
        assert c.put(f"/api/work-items/{i}/points", json={"points": 1, "source": "mcp"}).status_code == 200


def test_points_on_unknown_item_is_404(client):
    assert (
        client.put(f"/api/work-items/{uuid4()}/points", json={"points": 1, "source": "mcp"}).status_code
        == 404
    )
    assert client.get(f"/api/work-items/{uuid4()}/points").status_code == 404


def test_points_on_deleted_item_is_404_but_closed_item_is_fine(client, plane, pg_urls):
    p = plane.project("HOME")
    done = plane.item(p, "done", plane.state(p, "completed"))
    gone = plane.item(p, "gone", plane.state(p, "unstarted"))
    with psycopg.connect(pg_urls["admin"], autocommit=True) as conn:
        conn.execute("UPDATE public.issues SET deleted_at = now() WHERE id = %s", (gone,))
    body = {"points": 2, "source": "martin"}
    assert client.put(f"/api/work-items/{done}/points", json=body).status_code == 200
    assert client.put(f"/api/work-items/{gone}/points", json=body).status_code == 404
    assert client.get(f"/api/work-items/{gone}/points").status_code == 404


def test_if_unestimated_sets_when_empty(client, plane):
    p = plane.project("HOME")
    i = plane.item(p, "x", plane.state(p, "unstarted"))
    r = client.put(
        f"/api/work-items/{i}/points", json={"points": 2, "source": "claude-estimate", "if_unestimated": True}
    )
    assert (r.status_code, r.json()["points"], r.json()["points_source"]) == (200, 2, "claude-estimate")
    assert r.json()["updated_at"] is not None


def test_if_unestimated_refuses_to_overwrite(client, plane):  # Review Focus 5
    p = plane.project("HOME")
    i = plane.item(p, "x", plane.state(p, "unstarted"))
    client.put(f"/api/work-items/{i}/points", json={"points": 5, "source": "martin"})
    r = client.put(
        f"/api/work-items/{i}/points", json={"points": 2, "source": "claude-estimate", "if_unestimated": True}
    )
    assert r.status_code == 409
    got = client.get(f"/api/work-items/{i}/points").json()
    assert (got["points"], got["points_source"]) == (5, "martin")


def test_plain_put_overwrites(client, plane):
    p = plane.project("HOME")
    i = plane.item(p, "x", plane.state(p, "unstarted"))
    client.put(f"/api/work-items/{i}/points", json={"points": 5, "source": "claude-estimate"})
    r = client.put(f"/api/work-items/{i}/points", json={"points": 8, "source": "martin"})
    assert (r.json()["points"], r.json()["points_source"]) == (8, "martin")


def test_project_meta_by_identifier_case_insensitive(client, plane):
    pid = plane.project("NAKIS")
    r = client.put(
        "/api/projects/nakis",
        json={
            "repo": "nakomis/nakom.is",
            "deploys": True,
            "deploy_action": "Approve the prod deploy in GitHub Actions",
        },
    )
    assert r.json()["id"] == str(pid) and r.json()["bau_enabled"] is False
    assert client.get(f"/api/projects/{pid}").json()["repo"] == "nakomis/nakom.is"
    assert client.put("/api/projects/NAKIS", json={"repo": "not a repo"}).status_code == 422
    assert client.get("/api/projects/NOPE").status_code == 404


def test_project_meta_defaults_partial_update_and_clearing_repo(client, plane):
    pid = plane.project("HOME")
    got = client.get(f"/api/projects/{pid}").json()
    assert (got["repo"], got["deploys"], got["deploy_action"], got["bau_enabled"], got["column"]) == (
        None,
        False,
        "",
        False,
        "backlog",
    )
    client.put(f"/api/projects/{pid}", json={"repo": "nakomis/home", "bau_enabled": True})
    r = client.put(f"/api/projects/{pid}", json={"deploys": True}).json()
    assert (r["repo"], r["bau_enabled"], r["deploys"]) == ("nakomis/home", True, True)
    assert client.put(f"/api/projects/{pid}", json={"repo": None}).json()["repo"] is None
    assert client.put(f"/api/projects/{pid}", json={"deploys": None}).status_code == 422
    assert [m["identifier"] for m in client.get("/api/projects?bau_enabled=true").json()] == ["HOME"]


@pytest.mark.parametrize("repo", ["nakomis", "a/b/c", "a b/c", "/c", "a/", "a_b/c"])
def test_repo_must_look_like_owner_slash_name(client, plane, repo):
    plane.project("HOME")
    assert client.put("/api/projects/HOME", json={"repo": repo}).status_code == 422


def test_project_meta_unknown_uuid_and_archived_are_404(client, plane):
    old = plane.project("OLD", archived=True)
    assert client.get(f"/api/projects/{uuid4()}").status_code == 404
    assert client.put(f"/api/projects/{old}", json={"deploys": True}).status_code == 404
    assert client.put("/api/projects/OLD", json={"deploys": True}).status_code == 404


def test_project_meta_write_keeps_a_rowless_project_where_it_was(client, plane):
    a, b, c = plane.project("AAA"), plane.project("BBB"), plane.project("CCC")
    for p in (a, b, c):
        plane.item(p, "x", plane.state(p, "unstarted"))
    move(client, "project", c, "backlog", before=a)  # CCC ranked, so above rowless AAA, BBB
    before = [x["identifier"] for x in cols(client)["backlog"]["cards"]]
    assert before == ["CCC", "AAA", "BBB"]
    client.put("/api/projects/AAA", json={"repo": "nakomis/aaa"})
    after = [x["identifier"] for x in cols(client)["backlog"]["cards"]]
    assert after == before


def test_hidden_row_is_no_row_for_every_field(client, plane, pg_urls):
    pid = plane.project("HOME")
    plane.item(pid, "x", plane.state(pid, "unstarted"))
    client.put(f"/api/projects/{pid}", json={"repo": "nakomis/home", "bau_enabled": True, "deploys": True})
    move(client, "project", pid, "next")
    with psycopg.connect(pg_urls["admin"], autocommit=True) as conn:
        conn.execute("UPDATE atc.project SET hidden_at = now()")
    got = client.get(f"/api/projects/{pid}").json()
    assert (got["column"], got["repo"], got["deploys"], got["bau_enabled"]) == ("backlog", None, False, False)
    assert client.get("/api/projects?bau_enabled=true").json() == []
    # Writing revives the row from defaults, not from the stale hidden metadata.
    r = client.put(f"/api/projects/{pid}", json={"deploy_action": "go"}).json()
    assert (r["repo"], r["deploys"], r["bau_enabled"], r["deploy_action"]) == (None, False, False, "go")


def test_unestimated_list(client, plane):
    p = plane.project("HOME")
    s = plane.state(p, "unstarted")
    a = plane.item(p, "a", s)
    b = plane.item(p, "b", s)
    client.put(f"/api/work-items/{a}/points", json={"points": 1, "source": "mcp"})
    got = client.get("/api/work-items?project=HOME&unestimated=true").json()
    assert [(x["id"], x["ref"], x["module"]) for x in got] == [(str(b), "HOME-2", "Unsorted")]
    assert set(got[0]) == {"id", "ref", "name", "description", "module", "state_group"}


def test_unestimated_list_scope_description_and_module(client, plane, pg_urls):
    p, q = plane.project("HOME"), plane.project("OTHER")
    s, t = plane.state(p, "unstarted"), plane.state(q, "unstarted")
    m = plane.module(p, "Mod")
    long = plane.item(p, "long", s, modules=[m], sort_order=1.0)
    plane.item(p, "closed", plane.state(p, "completed"))
    plane.item(q, "elsewhere", t)
    with psycopg.connect(pg_urls["admin"], autocommit=True) as conn:
        conn.execute("UPDATE public.issues SET description_stripped = %s WHERE id = %s", ("x" * 2500, long))
    got = client.get("/api/work-items?project=home&unestimated=true").json()
    assert [(x["name"], x["module"], x["state_group"]) for x in got] == [("long", "Mod", "unstarted")]
    assert len(got[0]["description"]) == 2000
    assert client.get("/api/work-items?project=NOPE&unestimated=true").status_code == 404
    assert client.get("/api/work-items?project=HOME").status_code == 422


def test_store_update_project_meta_without_rank_goes_after_ranked_backlog(atc_conn):
    from atc import store

    first, second = uuid4(), uuid4()
    one = store.update_project_meta(atc_conn, first, repo="nakomis/one")
    two = store.update_project_meta(atc_conn, second)
    assert (one.column_key, two.column_key) == ("backlog", "backlog")
    assert one.rank < two.rank and one.repo == "nakomis/one"


def test_store_update_project_meta_refuses_unknown_fields(atc_conn):
    from atc import store

    with pytest.raises(TypeError):
        store.update_project_meta(atc_conn, uuid4(), colour="red")
