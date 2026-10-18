"""FastAPI application. Run with `uvicorn atc.app:create_app --factory`."""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator

from atc import db, moves, ordering, store
from atc import reconcile as reconciler
from atc.board import build_board, priority_modules
from atc.plane import missing_columns, read_plane
from atc.settings import Settings
from atc.store import MOVE_LOCK_KEY, AlreadySet, load_rows

log = logging.getLogger(__name__)


class MoveBody(BaseModel):
    kind: Literal["project", "module"]
    id: UUID
    to_column: str
    before_id: UUID | None = None


class ReorderBody(BaseModel):
    project_id: UUID
    module_id: UUID
    before_id: UUID | None = None


REPO_PATTERN = re.compile(r"^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$")
DESCRIPTION_LIMIT = 2000


class PointsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    points: StrictInt = Field(ge=1)  # the upper bound is Settings.max_points, checked in the route
    source: Literal["claude-estimate", "martin", "mcp"]
    if_unestimated: StrictBool = False


class ProjectMetaBody(BaseModel):
    """Only the fields sent are changed; `repo: null` clears the repo."""

    model_config = ConfigDict(extra="forbid")
    repo: str | None = None
    deploys: StrictBool | None = None
    deploy_action: str | None = None
    bau_enabled: StrictBool | None = None

    @field_validator("repo")
    @classmethod
    def _repo_shape(cls, v: str | None) -> str | None:
        if v is not None and not REPO_PATTERN.fullmatch(v):
            raise ValueError("repo must look like owner/name")
        return v

    @field_validator("deploys", "deploy_action", "bau_enabled", mode="before")
    @classmethod
    def _not_null(cls, v):
        if v is None:
            raise ValueError("may be omitted but not null")
        return v


@dataclass
class ReconcileState:
    """What the background reconcile last did; read by /api/health."""

    last_ok: datetime | None = None  # when the last successful pass started
    failed: bool = False  # the most recent attempt raised


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    state = ReconcileState()

    def reconcile_once(pool) -> None:
        """One pass; a failure is logged and recorded, never raised."""
        try:
            with pool.connection() as conn:
                result = reconciler.reconcile(conn, settings.workspace_slug)
            state.last_ok, state.failed = result.at, False
            if result.missing:
                log.error("reconcile skipped: Plane columns not visible to atc: %s", result.missing)
        except Exception:
            state.failed = True
            log.exception("reconcile failed")

    def reconcile_loop(pool, stop: threading.Event) -> None:
        while not stop.is_set():
            reconcile_once(pool)
            stop.wait(settings.reconcile_seconds)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        pool = db.open_pool(settings.database_url)
        stop = threading.Event()
        worker: threading.Thread | None = None
        try:
            version = db.migrate(pool)
            log.info("atc schema at version %s", version)
            app.state.pool = pool
            # Once at start-up, then every reconcile_seconds; 0 turns the loop off (tests call it directly).
            if settings.reconcile_seconds > 0:
                worker = threading.Thread(
                    target=reconcile_loop, args=(pool, stop), name="reconcile", daemon=True
                )
                worker.start()
            yield
        finally:
            stop.set()
            if worker is not None:
                worker.join(timeout=30)
            pool.close()

    app = FastAPI(title="ATC", lifespan=lifespan)
    app.state.settings = settings

    @app.get("/api/health")
    def health(request: Request) -> JSONResponse:
        try:
            with request.app.state.pool.connection(timeout=5) as conn:
                missing = missing_columns(conn)
                hidden = {
                    "projects": conn.execute(
                        "SELECT count(*) FROM atc.project WHERE hidden_at IS NOT NULL"
                    ).fetchone()[0],
                    "modules": conn.execute(
                        "SELECT count(*) FROM atc.module WHERE hidden_at IS NOT NULL"
                    ).fetchone()[0],
                }
            ok = not missing and not state.failed
        except Exception:
            log.exception("health check could not reach the database")
            ok, missing, hidden = False, [], {"projects": 0, "modules": 0}
        body = {
            "ok": ok,
            "missing": missing,
            "last_reconcile": state.last_ok.isoformat() if state.last_ok else None,
            "hidden": hidden,
        }
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

    def resolve_project(snap, ref: str) -> UUID:
        """A live project's id from a UUID or an identifier (case-insensitive); 404 otherwise."""
        try:
            pid = UUID(ref)
            if any(p.id == pid for p in snap.projects):
                return pid
        except ValueError:
            wanted = ref.upper()
            for p in snap.projects:
                if p.identifier.upper() == wanted:
                    return p.id
        raise HTTPException(404, f"no project {ref}")

    def meta_of(request: Request, ref: str) -> dict:
        built, snap, rows = read_board(request)
        pid = resolve_project(snap, ref)
        return ordering.project_meta(built.projects, rows, pid, {c.key for c in rows.columns})

    @app.get("/api/projects/{ref}")
    def project_get(ref: str, request: Request) -> dict:
        return meta_of(request, ref)

    @app.put("/api/projects/{ref}")
    def project_put(ref: str, body: ProjectMetaBody, request: Request) -> dict:
        fields = {k: getattr(body, k) for k in body.model_fields_set}
        with request.app.state.pool.connection() as conn:
            with conn.transaction():
                conn.execute("SELECT pg_advisory_xact_lock(%s)", (MOVE_LOCK_KEY,))
                snap = read_plane(conn, settings.workspace_slug)
                pid = resolve_project(snap, ref)
                rows = load_rows(conn)
                row = rows.projects.get(pid)
                rank = None
                if row is None:  # rowless: keep its place in Backlog
                    rank = moves.backlog_rank_in_place(conn, snap, rows, pid)
                store.update_project_meta(conn, pid, rank=rank, **fields)
        return meta_of(request, str(pid))

    def live_item(conn, item_id: UUID) -> None:
        """404 unless Plane has the item undeleted (closed and archived items still take points)."""
        found = conn.execute(
            "SELECT 1 FROM public.issues i"
            " JOIN public.projects p ON p.id = i.project_id AND p.deleted_at IS NULL"
            " JOIN public.workspaces w ON w.id = p.workspace_id AND w.deleted_at IS NULL"
            " WHERE i.id = %s AND i.deleted_at IS NULL AND w.slug = %s",
            (item_id, settings.workspace_slug),
        ).fetchone()
        if found is None:
            raise HTTPException(404, f"no work item {item_id}")

    def points_json(item_id: UUID, row: store.PointsRow | None) -> dict:
        return {
            "id": str(item_id),
            "points": row.points if row else None,
            "points_source": row.source if row else None,
            "updated_at": row.updated_at.isoformat() if row else None,
        }

    @app.get("/api/work-items/{item_id}/points")
    def points_get(item_id: UUID, request: Request) -> dict:
        with request.app.state.pool.connection() as conn:
            live_item(conn, item_id)
            return points_json(item_id, load_rows(conn).points.get(item_id))

    @app.put("/api/work-items/{item_id}/points")
    def points_put(item_id: UUID, body: PointsBody, request: Request) -> dict:
        if body.points > settings.max_points:
            raise HTTPException(422, f"points must be 1..{settings.max_points}")
        with request.app.state.pool.connection() as conn:
            with conn.transaction():
                conn.execute("SELECT pg_advisory_xact_lock(%s)", (MOVE_LOCK_KEY,))
                live_item(conn, item_id)
                try:
                    row = store.set_points(
                        conn, item_id, body.points, body.source, if_unestimated=body.if_unestimated
                    )
                except AlreadySet as e:
                    raise HTTPException(409, "already estimated; not overwritten") from e
        return points_json(item_id, row)

    @app.get("/api/work-items")
    def unestimated(request: Request, unestimated: bool = False, project: str | None = None) -> list[dict]:
        if not unestimated:
            raise HTTPException(422, "only unestimated=true is supported")
        built, snap, _ = read_board(request)
        wanted = resolve_project(snap, project) if project is not None else None
        found = [
            (m, i)
            for m in priority_modules(built)
            if wanted is None or m.project_id == wanted
            for i in m.items
            if i.points is None
        ]
        with request.app.state.pool.connection() as conn:
            described = dict(
                conn.execute(
                    "SELECT id, left(coalesce(description_stripped, ''), %s) FROM public.issues"
                    " WHERE id = ANY(%s)",
                    (DESCRIPTION_LIMIT, [i.id for _, i in found]),
                ).fetchall()
            )
        return [
            {
                "id": str(i.id),
                "ref": i.ref,
                "name": i.name,
                "description": described.get(i.id, ""),
                "module": m.name,
                "state_group": i.state_group,
            }
            for m, i in found
        ]

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
