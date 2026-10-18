"""Shared helpers for API tests."""

from __future__ import annotations

import psycopg
from fastapi.testclient import TestClient


def col(board_json: dict, key: str) -> dict:
    """The column with `key` from a board response."""
    for column in board_json["columns"]:
        if column["key"] == key:
            return column
    raise KeyError(key)


def cols(client: TestClient) -> dict[str, dict]:
    """`GET /api/board` columns keyed by `key`."""
    r = client.get("/api/board")
    assert r.status_code == 200, r.text
    return {c["key"]: c for c in r.json()["columns"]}


def move(client: TestClient, kind: str, id, to_column: str, before=None) -> dict[str, dict]:
    """`POST /api/move`; asserts 200 and returns the board's columns keyed by `key`."""
    body = {"kind": kind, "id": str(id), "to_column": to_column}
    if before is not None:
        body["before_id"] = str(before)
    r = client.post("/api/move", json=body)
    assert r.status_code == 200, r.text
    return {c["key"]: c for c in r.json()["columns"]}


def updated_rows(pg_urls: dict[str, str]) -> set[tuple]:
    """`(table, id, updated_at)` for every row of atc.project and atc.module."""
    with psycopg.connect(pg_urls["admin"]) as conn:
        return {
            *(("project", *r) for r in conn.execute("SELECT plane_id, updated_at FROM atc.project")),
            *(("module", *r) for r in conn.execute("SELECT id, updated_at FROM atc.module")),
        }
