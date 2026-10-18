"""FastAPI application. Run with `uvicorn atc.app:create_app --factory`."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Literal
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from atc import db, moves, ordering
from atc.board import build_board
from atc.plane import read_plane
from atc.settings import Settings
from atc.store import load_rows

log = logging.getLogger(__name__)

# Fixed for ever: concurrent drags queue on it, so each places against the board as the last left it.
MOVE_LOCK_KEY = 0x41544301


class MoveBody(BaseModel):
    kind: Literal["project", "module"]
    id: UUID
    to_column: str
    before_id: UUID | None = None


class ReorderBody(BaseModel):
    project_id: UUID
    module_id: UUID
    before_id: UUID | None = None


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        pool = db.open_pool(settings.database_url)
        try:
            version = db.migrate(pool)
            log.info("atc schema at version %s", version)
            app.state.pool = pool
            yield
        finally:
            pool.close()

    app = FastAPI(title="ATC", lifespan=lifespan)
    app.state.settings = settings

    @app.get("/api/health")
    def health(request: Request) -> JSONResponse:
        # Placeholder until Task 8: reports only whether the database answers.
        try:
            with request.app.state.pool.connection(timeout=5) as conn:
                conn.execute("SELECT 1")
            ok = True
        except Exception:
            log.exception("health check could not reach the database")
            ok = False
        body = {"ok": ok, "missing": [], "last_reconcile": None, "hidden": {"projects": 0, "modules": 0}}
        return JSONResponse(body, status_code=200 if ok else 503)

    def link(ref: str) -> str:
        return f"{settings.plane_web_url}/{settings.workspace_slug}/browse/{ref}/"

    @app.get("/api/board")
    def board(request: Request, include_all: Annotated[bool, Query(alias="all")] = False) -> dict:
        with request.app.state.pool.connection() as conn:
            # One read-only snapshot, so Plane's rows and ATC's agree with each other.
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            snap = read_plane(conn, settings.workspace_slug)
            rows = load_rows(conn)
        built = build_board(snap, rows, include_all=include_all, link=link, max_points=settings.max_points)
        return built.to_json()

    def read_board(request: Request):
        """One read-only snapshot, laid out as the default board (open work only)."""
        with request.app.state.pool.connection() as conn:
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            snap = read_plane(conn, settings.workspace_slug)
            rows = load_rows(conn)
        built = build_board(snap, rows, include_all=False, link=link, max_points=settings.max_points)
        return built, snap, rows

    @app.get("/api/next")
    def next_up(request: Request) -> dict:
        built, _, _ = read_board(request)
        column, found = ordering.next_items(built)
        return {
            "column": column,
            "next": found[0] if found else None,
            "runners_up": found[1:],
        }

    @app.get("/api/priority")
    def priority(request: Request) -> dict:
        built, _, _ = read_board(request)
        return {"refs": ordering.priority_refs(built)}

    @app.get("/api/projects")
    def projects(request: Request, bau_enabled: bool | None = None) -> list[dict]:
        built, snap, rows = read_board(request)
        columns = {c.key for c in rows.columns}
        metas = [
            ordering.project_meta(built.projects, rows, pid, columns)
            for pid in ordering.projects_in_priority(built, snap, rows)
        ]
        if bau_enabled is not None:
            metas = [m for m in metas if m["bau_enabled"] == bau_enabled]
        return metas

    def write(request: Request, include_all: bool, change) -> dict:
        """Apply `change(conn, snap, rows)` in one transaction, then return the board as it now stands."""
        with request.app.state.pool.connection() as conn:
            with conn.transaction():
                conn.execute("SELECT pg_advisory_xact_lock(%s)", (MOVE_LOCK_KEY,))
                snap = read_plane(conn, settings.workspace_slug)
                try:
                    change(conn, snap, load_rows(conn))
                except moves.NotFound as e:
                    raise HTTPException(404, str(e)) from e
                except moves.Invalid as e:
                    raise HTTPException(422, str(e)) from e
            rows = load_rows(conn)
        built = build_board(snap, rows, include_all=include_all, link=link, max_points=settings.max_points)
        return built.to_json()

    # The bodies are pydantic models, so FastAPI refuses anything not sent as JSON: a cross-site
    # form post cannot drive a move.
    @app.post("/api/move")
    def move(
        body: MoveBody, request: Request, include_all: Annotated[bool, Query(alias="all")] = False
    ) -> dict:
        return write(
            request,
            include_all,
            lambda conn, snap, rows: moves.move(
                conn,
                snap,
                rows,
                kind=body.kind,
                id=body.id,
                to_column=body.to_column,
                before_id=body.before_id,
            ),
        )

    @app.post("/api/reorder")
    def reorder(
        body: ReorderBody, request: Request, include_all: Annotated[bool, Query(alias="all")] = False
    ) -> dict:
        return write(
            request,
            include_all,
            lambda conn, snap, rows: moves.reorder(
                conn,
                snap,
                rows,
                project_id=body.project_id,
                module_id=body.module_id,
                before_id=body.before_id,
            ),
        )

    return app
