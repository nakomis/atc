"""FastAPI application. Run with `uvicorn atc.app:create_app --factory`."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse

from atc import db
from atc.board import build_board
from atc.plane import read_plane
from atc.settings import Settings
from atc.store import load_rows

log = logging.getLogger(__name__)


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

    return app
