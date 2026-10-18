"""Keeps ATC's rows in step with Plane (spec §11): creates rows for new work, hides rows for gone work.

Rows are created lazily by moves, so a reconcile only has to (a) give brand-new Plane projects and
modules a place at the bottom of Backlog, (b) hide rows whose Plane project or module is deleted or
archived, and (c) unhide rows whose Plane row is back. It never deletes anything, never touches
`atc.work_item`, and never moves a row that exists: inserts are `ON CONFLICT DO NOTHING`.

Every write happens under the same advisory lock as moves and metadata writes, so a move's upsert
(which clears `hidden_at`) cannot interleave with a hide.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import psycopg

from atc import moves, ranks
from atc.board import DEFAULT_COLUMN, unsorted_id
from atc.plane import missing_columns, read_plane
from atc.store import MOVE_LOCK_KEY, backlog_max_rank, load_rows

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReconcileResult:
    created_projects: int
    created_modules: int  # module rows, Unsorted groups included
    hidden: int  # rows, projects and modules together
    unhidden: int
    missing: list[str]
    at: datetime


def reconcile(conn: psycopg.Connection, workspace_slug: str) -> ReconcileResult:
    """One reconcile pass in a single REPEATABLE READ transaction; LookupError if the workspace is unseen.

    The move lock is taken first, as a session-level lock in its own short transaction, and only
    then does the REPEATABLE READ transaction (and its snapshot) begin. Every other writer takes the
    same lock, so nothing can commit between the snapshot and reconcile's writes, and a pass that
    waited for a busy board does not fail with a serialisation conflict.

    If any required Plane column is invisible to the `atc` role nothing is written and `missing`
    says which; the caller reports it through /api/health.
    """
    at = datetime.now(UTC)
    with conn.transaction():
        conn.execute("SELECT pg_advisory_lock(%s)", (MOVE_LOCK_KEY,))
    try:
        with conn.transaction():
            # One snapshot for every read below, so projects, modules and ATC's rows agree.
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            return _pass(conn, workspace_slug, at)
    finally:
        try:
            with conn.transaction():
                conn.execute("SELECT pg_advisory_unlock(%s)", (MOVE_LOCK_KEY,))
        except psycopg.Error:
            # A session that cannot unlock must not go back to the pool holding the lock.
            log.exception("reconcile could not release the move lock; closing its connection")
            conn.close()


def _pass(conn: psycopg.Connection, workspace_slug: str, at: datetime) -> ReconcileResult:
    """The body of a pass: runs inside reconcile's transaction, with the move lock held."""
    missing = missing_columns(conn)
    if missing:
        return ReconcileResult(0, 0, 0, 0, missing, at)
    # An unreadable or misnamed workspace would look like "everything is gone"; refuse to hide on it.
    if (
        conn.execute(
            "SELECT 1 FROM public.workspaces WHERE slug = %s AND deleted_at IS NULL", (workspace_slug,)
        ).fetchone()
        is None
    ):
        raise LookupError(f"workspace {workspace_slug!r} not found in Plane")
    snap = read_plane(conn, workspace_slug)

    live_projects = [p.id for p in snap.projects]
    live_modules = [m.id for m in snap.modules] + [unsorted_id(p) for p in live_projects]
    hidden = _flip(conn, "atc.project", "plane_id", live_projects, hide=True)
    hidden += _flip(conn, "atc.module", "id", live_modules, hide=True)
    unhidden = _flip(conn, "atc.project", "plane_id", live_projects, hide=False)
    unhidden += _flip(conn, "atc.module", "id", live_modules, hide=False)

    rows = load_rows(conn)
    tail = backlog_max_rank(conn)  # the last rank handed out in Backlog, advanced as we insert
    card_tail: dict[UUID, str | None] = {}
    for r in rows.modules.values():
        if r.hidden_at is None and (card_tail.get(r.project_id) or "") < r.card_rank:
            card_tail[r.project_id] = r.card_rank

    created_projects = created_modules = 0
    modules_of: dict[UUID, list] = {}
    for m in snap.modules:
        modules_of.setdefault(m.project_id, []).append(m)

    rebalanced = False

    def next_tail() -> str:
        nonlocal tail, rebalanced
        tail = ranks.after(tail)
        if len(tail) > ranks.REBALANCE_LENGTH and not rebalanced:  # Backlog's bottom is long
            moves.rebalance_column(conn, snap, DEFAULT_COLUMN)
            rebalanced = True  # once per pass, whatever is left over
            tail = ranks.after(backlog_max_rank(conn))
        return tail

    for p in snap.projects:
        existing = rows.projects.get(p.id)
        column = existing.column_key if existing else DEFAULT_COLUMN
        if existing is None:
            created_projects += _insert_project(conn, p.id, next_tail())
        # (id, project column or Backlog): new modules are Backlog cards; Unsorted follows its project.
        wanted = [(m.id, False, DEFAULT_COLUMN) for m in modules_of.get(p.id, [])]
        wanted.append((unsorted_id(p.id), True, column))
        for module_id, unsorted, column_key in wanted:
            if module_id in rows.modules:
                continue
            card_tail[p.id] = card = ranks.after(card_tail.get(p.id))
            created_modules += _insert_module(conn, module_id, p.id, unsorted, column_key, next_tail(), card)
    return ReconcileResult(created_projects, created_modules, hidden, unhidden, [], at)


def _flip(conn: psycopg.Connection, table: str, key: str, live: list[UUID], *, hide: bool) -> int:
    """Hide rows of `table` not in `live` (or unhide those that are); the number of rows changed."""
    if hide:
        sql = (
            f"UPDATE {table} SET hidden_at = now(), updated_at = now()"
            f" WHERE hidden_at IS NULL AND {key} <> ALL(%s)"
        )
    else:
        sql = (
            f"UPDATE {table} SET hidden_at = NULL, updated_at = now()"
            f" WHERE hidden_at IS NOT NULL AND {key} = ANY(%s)"
        )
    return conn.execute(sql, (live,)).rowcount


def _insert_project(conn: psycopg.Connection, project_id: UUID, rank: str) -> int:
    return conn.execute(
        "INSERT INTO atc.project (plane_id, column_key, rank) VALUES (%s, %s, %s)"
        " ON CONFLICT (plane_id) DO NOTHING",
        (project_id, DEFAULT_COLUMN, rank),
    ).rowcount


def _insert_module(
    conn: psycopg.Connection,
    module_id: UUID,
    project_id: UUID,
    unsorted: bool,
    column_key: str,
    column_rank: str,
    card_rank: str,
) -> int:
    return conn.execute(
        "INSERT INTO atc.module (id, project_id, unsorted, column_key, column_rank, card_rank)"
        " VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
        (module_id, project_id, unsorted, column_key, column_rank, card_rank),
    ).rowcount
