"""FastAPI application. Run with `uvicorn atc.app:create_app --factory`."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from atc import db
from atc.settings import Settings

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

    return app
