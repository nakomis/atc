"""Shared helpers for API tests."""

from __future__ import annotations

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
