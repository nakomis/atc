from uuid import uuid4

import psycopg
import pytest
from helpers import col, cols, move, updated_rows

from atc import moves, ranks
from atc.board import unsorted_id


def setup_three(plane, client):
    """Project HOME with modules M1, M2, M3, one open item each; M3 moved to In progress."""
    home = plane.project("HOME")
    s = plane.state(home, "unstarted")
    mods = tuple(plane.module(home, name) for name in ("M1", "M2", "M3"))
    for n, m in enumerate(mods, 1):
        plane.item(home, f"item {n}", s, modules=[m])
    move(client, "module", mods[2], "in_progress")
    return home, mods


def names(card):
    return [m["name"] for m in card["modules"]]


# --- The brief's tests -------------------------------------------------------------------


def test_move_module_to_other_column_makes_module_card(client, plane):
    home, (m1, m2, m3) = setup_three(plane, client)
    b = move(client, "module", m2, "next")
    [card] = b["next"]["cards"]
    assert (card["kind"], card["label"]) == ("module", "HOME · M2")


def test_move_module_into_its_projects_column_joins_card_at_bottom(client, plane):
    home, (m1, m2, m3) = setup_three(plane, client)
    b = move(client, "module", m3, "backlog")
    assert [m["name"] for m in b["backlog"]["cards"][0]["modules"]] == ["M1", "M2", "M3"]


def test_project_move_takes_source_and_target_modules_not_third(client, plane):
    home, (m1, m2, m3) = setup_three(plane, client)
    move(client, "module", m2, "next")
    b = move(client, "project", home, "next")
    [card] = b["next"]["cards"]
    assert [m["name"] for m in card["modules"]] == ["M2", "M1"]  # B's first, then A's
    assert b["backlog"]["cards"] == []
    assert b["in_progress"]["cards"][0]["label"] == "HOME · M3"


def test_before_id_places_card(client, plane):
    a = plane.project("AAA")
    z = plane.project("ZZZ")
    for p in (a, z):
        plane.item(p, "x", plane.state(p, "unstarted"))
    move(client, "project", a, "next")
    b = move(client, "project", z, "next", before=a)
    assert [c["identifier"] for c in b["next"]["cards"]] == ["ZZZ", "AAA"]


def test_reorder_within_project_card_writes_one_row(client, plane, pg_urls):
    home, (m1, m2, m3) = setup_three(plane, client)
    move(client, "module", m3, "backlog")
    before = updated_rows(pg_urls)
    r = client.post(
        "/api/reorder", json={"project_id": str(home), "module_id": str(m3), "before_id": str(m1)}
    )
    assert [m["name"] for m in col(r.json(), "backlog")["cards"][0]["modules"]] == ["M3", "M1", "M2"]
    assert len(updated_rows(pg_urls) - before) == 1


def test_bad_requests(client, plane):
    home, (m1, m2, m3) = setup_three(plane, client)
    assert (
        client.post("/api/move", json={"kind": "module", "id": str(uuid4()), "to_column": "next"}).status_code
        == 404
    )
    assert (
        client.post("/api/move", json={"kind": "module", "id": str(m1), "to_column": "nope"}).status_code
        == 422
    )
    assert (
        client.post(
            "/api/move", json={"kind": "module", "id": str(m1), "to_column": "next", "before_id": str(m1)}
        ).status_code
        == 422
    )


def test_non_json_post_is_refused(client, plane):  # no CSRF via form posts
    home, (m1, *_) = setup_three(plane, client)
    r = client.post(
        "/api/move",
        content=f'{{"kind":"module","id":"{m1}","to_column":"next"}}',
        headers={"content-type": "text/plain"},
    )
    assert r.status_code in (415, 422)


def test_db_orders_ranks_bytewise(pg_urls, migrated):  # Review Focus 3
    with psycopg.connect(pg_urls["atc"]) as c:
        got = [
            r[0]
            for r in c.execute("SELECT k FROM (VALUES ('a'), ('B'), ('0z')) v(k) ORDER BY k COLLATE \"C\"")
        ]
        cols_ = {
            r[0]: r[1]
            for r in c.execute(
                "SELECT column_name, collation_name FROM information_schema.columns "
                "WHERE table_schema='atc' AND column_name IN ('rank','column_rank','card_rank')"
            )
        }
    assert got == ["0z", "B", "a"] and set(cols_.values()) == {"C"}


# --- Further cases ------------------------------------------------------------------------


def test_project_move_within_column_reorders_the_card(client, plane):
    projects = [plane.project(i) for i in ("AAA", "BBB", "CCC")]
    for p in projects:
        plane.item(p, "x", plane.state(p, "unstarted"))
    # All rowless in Backlog: AAA, BBB, CCC by creation. Put CCC first.
    b = move(client, "project", projects[2], "backlog", before=projects[0])
    assert [c["identifier"] for c in b["backlog"]["cards"]] == ["CCC", "AAA", "BBB"]
    # Now to the bottom, past rowless cards.
    b = move(client, "project", projects[2], "backlog")
    assert [c["identifier"] for c in b["backlog"]["cards"]] == ["AAA", "BBB", "CCC"]


def test_before_a_rowless_card_ranks_the_cards_ahead_of_it(client, plane):
    projects = [plane.project(i) for i in ("AAA", "BBB", "CCC", "DDD")]
    for p in projects:
        plane.item(p, "x", plane.state(p, "unstarted"))
    b = move(client, "project", projects[3], "backlog", before=projects[2])
    assert [c["identifier"] for c in b["backlog"]["cards"]] == ["AAA", "BBB", "DDD", "CCC"]
    b = move(client, "project", projects[0], "backlog", before=projects[3])
    assert [c["identifier"] for c in b["backlog"]["cards"]] == ["BBB", "AAA", "DDD", "CCC"]


def test_module_card_placed_before_a_project_card(client, plane):
    home, (m1, m2, m3) = setup_three(plane, client)
    other = plane.project("OTH")
    plane.item(other, "x", plane.state(other, "unstarted"))
    move(client, "project", other, "in_progress", before=m3)
    b = move(client, "module", m1, "in_progress", before=other)
    assert [c["label"] for c in b["in_progress"]["cards"]] == ["HOME · M1", "OTH project", "HOME · M3"]


def test_module_card_reordered_within_its_column(client, plane):
    home, (m1, m2, m3) = setup_three(plane, client)
    move(client, "module", m1, "in_progress")
    b = move(client, "module", m1, "in_progress", before=m3)
    assert [c["label"] for c in b["in_progress"]["cards"]] == ["HOME · M1", "HOME · M3"]


def test_module_already_in_its_project_card_stays_put(client, plane, pg_urls):
    home, (m1, m2, m3) = setup_three(plane, client)
    before = updated_rows(pg_urls)
    b = move(client, "module", m1, "backlog")
    assert names(b["backlog"]["cards"][0]) == ["M1", "M2"]
    assert updated_rows(pg_urls) == before


def test_project_move_with_before_id_on_an_absorbed_module_card(client, plane):
    home, (m1, m2, m3) = setup_three(plane, client)
    other = plane.project("OTH")
    plane.item(other, "x", plane.state(other, "unstarted"))
    move(client, "project", other, "in_progress")  # In progress: HOME · M3, OTH
    b = move(client, "project", home, "in_progress", before=m3)
    assert [c["label"] for c in b["in_progress"]["cards"]] == ["HOME project", "OTH project"]
    assert names(b["in_progress"]["cards"][0]) == ["M3", "M1", "M2"]


def test_unsorted_group_moves_as_a_module(client, plane):
    home = plane.project("HOME")
    plane.item(home, "loose", plane.state(home, "unstarted"))
    b = move(client, "module", unsorted_id(home), "next")
    [card] = b["next"]["cards"]
    assert (card["kind"], card["label"]) == ("module", "HOME · Unsorted")
    assert names(b["backlog"]["cards"][0]) == []


def test_project_card_follows_into_third_column_leaving_modules(client, plane):
    home, (m1, m2, m3) = setup_three(plane, client)
    move(client, "project", home, "next")  # takes M1, M2 from Backlog
    b = move(client, "project", home, "in_progress")  # takes M1, M2 from Next and M3 from In progress
    assert names(b["in_progress"]["cards"][0]) == ["M3", "M1", "M2"]
    assert b["next"]["cards"] == [] and b["backlog"]["cards"] == []


def test_move_refusals(client, plane):
    home, (m1, m2, m3) = setup_three(plane, client)
    other = plane.project("OTH")
    plane.item(other, "x", plane.state(other, "unstarted"))

    def post(**body):
        return client.post("/api/move", json={k: str(v) for k, v in body.items()}).status_code

    assert post(kind="project", id=uuid4(), to_column="next") == 404
    assert post(kind="project", id=home, to_column="next", before_id=other) == 422  # OTH is in Backlog
    assert post(kind="project", id=home, to_column="backlog", before_id=home) == 422
    assert post(kind="module", id=m1, to_column="next", before_id=uuid4()) == 422
    assert post(kind="widget", id=m1, to_column="next") == 422


def test_reorder_refusals(client, plane):
    home, (m1, m2, m3) = setup_three(plane, client)
    other = plane.project("OTH")
    om = plane.module(other, "O1")

    def post(project, module, before=None):
        body = {"project_id": str(project), "module_id": str(module)}
        if before is not None:
            body["before_id"] = str(before)
        return client.post("/api/reorder", json=body).status_code

    assert post(uuid4(), m1) == 404
    assert post(home, uuid4()) == 404
    assert post(home, om) == 422  # another project's module
    assert post(home, m3) == 422  # a module card, not in the project card
    assert post(home, m1, before=m3) == 422  # before_id outside the card
    assert post(home, m1, before=m1) == 422


def test_reorder_to_the_bottom_of_the_card(client, plane):
    home, (m1, m2, m3) = setup_three(plane, client)
    r = client.post("/api/reorder", json={"project_id": str(home), "module_id": str(m1)})
    assert r.status_code == 200, r.text
    assert names(col(r.json(), "backlog")["cards"][0]) == ["M2", "M1"]


def test_board_after_move_honours_all(client, plane):
    home, (m1, m2, m3) = setup_three(plane, client)
    r = client.post("/api/move?all=true", json={"kind": "module", "id": str(m2), "to_column": "next"})
    assert names(col(r.json(), "backlog")["cards"][0]) == ["M1", "Unsorted"]
    assert names(cols(client)["backlog"]["cards"][0]) == ["M1"]


# --- Placement ---------------------------------------------------------------------------


def test_place_between_ranked_neighbours():
    rank, filled = moves.place([("a", "1"), ("b", "3")], 1)
    assert "1" < rank < "3" and filled == []


def test_place_after_rowless_ranks_them():
    rank, filled = moves.place([("a", "1"), ("b", None), ("c", None)], 3)
    assert [k for k, _ in filled] == ["b", "c"]
    seq = ["1", *(r for _, r in filled), rank]
    assert seq == sorted(seq) and len(set(seq)) == 4


def test_place_with_duplicate_ranks_reranks_the_lot():
    rank, filled = moves.place([("a", "V"), ("b", "V")], 1)
    order = {k: r for k, r in filled} | {"new": rank}
    assert sorted(order, key=order.get) == ["a", "new", "b"]


def test_ten_thousand_bottom_appends_then_a_drop_keep_ranks_short():  # final review I2
    entries: list[tuple[int, str | None]] = []
    for n in range(10_000):
        rank, filled = moves.place(entries, len(entries))
        fixed = dict(filled)
        entries = [(k, fixed.get(k, r)) for k, r in entries] + [(n, rank)]
    rank, filled = moves.place(entries, len(entries))  # one more drop on the column's empty space
    fixed = dict(filled)
    entries = [(k, fixed.get(k, r)) for k, r in entries] + [("drop", rank)]
    rank, filled = moves.place(entries, 5_000)  # and one into the middle
    fixed = dict(filled)
    entries = [(k, fixed.get(k, r)) for k, r in entries]
    entries.insert(5_000, ("middle", rank))
    seq = [r for _, r in entries]
    assert seq == sorted(seq) and len(set(seq)) == len(seq)
    assert max(map(len, seq)) <= ranks.REBALANCE_LENGTH
    assert [k for k, _ in entries][4_999:5_001] == [4_999, "middle"]


def test_place_reranks_when_the_new_key_would_be_too_long():
    long = "z" * ranks.REBALANCE_LENGTH
    rank, filled = moves.place([("a", "1"), ("b", long)], 2)
    order = dict(filled) | {"new": rank}
    assert sorted(order, key=order.get) == ["a", "b", "new"]
    assert max(map(len, order.values())) <= 2


def test_drop_at_the_bottom_of_a_column_with_a_long_tail_rebalances(client, plane, pg_urls):
    a, b, c = (plane.project(name) for name in ("AAA", "BBB", "CCC"))
    for p in (a, b, c):
        plane.item(p, "x", plane.state(p, "unstarted"))
    move(client, "project", a, "next")
    move(client, "project", b, "next")
    with psycopg.connect(pg_urls["admin"]) as conn:  # as if after thousands of bottom drops
        conn.execute("UPDATE atc.project SET rank = %s WHERE plane_id = %s", ("z" * 990 + "1", b))
    board = move(client, "project", c, "next")
    assert [card["label"] for card in board["next"]["cards"]] == ["AAA project", "BBB project", "CCC project"]
    with psycopg.connect(pg_urls["admin"]) as conn:
        lengths = [len(r) for (r,) in conn.execute("SELECT rank FROM atc.project WHERE column_key = 'next'")]
    assert max(lengths) <= ranks.REBALANCE_LENGTH


def test_place_rejects_out_of_range():
    with pytest.raises(IndexError):
        moves.place([], 1)
    assert ranks.after(None)


def test_rowless_module_card_is_ranked_when_a_card_goes_below_it(client, plane, pg_urls):
    home, (m1, m2, m3) = setup_three(plane, client)
    move(client, "project", home, "next")
    other = plane.project("OTH")
    plane.item(other, "x", plane.state(other, "unstarted"))
    m4 = plane.module(home, "M4")  # new and rowless: a module card at the bottom of Backlog
    plane.item(home, "item 4", plane.state(home, "unstarted"), modules=[m4])
    assert [c["label"] for c in cols(client)["backlog"]["cards"]] == ["OTH project", "HOME · M4"]
    b = move(client, "project", other, "backlog")
    assert [c["label"] for c in b["backlog"]["cards"]] == ["HOME · M4", "OTH project"]
    with psycopg.connect(pg_urls["admin"]) as c:
        [(column, column_rank, card_rank)] = c.execute(
            "SELECT column_key, column_rank, card_rank FROM atc.module WHERE id = %s", (m4,)
        ).fetchall()
    assert column == "backlog" and column_rank == card_rank
