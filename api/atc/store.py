"""ATC's own rows in schema `atc`: columns, project and module placement, and points."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import psycopg

from atc import ranks


@dataclass(frozen=True)
class ColumnDef:
    key: str
    label: str
    position: int  # display order, left to right
    priority: int  # work order, 0 first


@dataclass(frozen=True)
class ProjectRow:
    plane_id: UUID
    column_key: str
    rank: str
    repo: str | None
    deploys: bool
    deploy_action: str
    bau_enabled: bool
    hidden_at: datetime | None


@dataclass(frozen=True)
class ModuleRow:
    id: UUID
    project_id: UUID
    unsorted: bool
    column_key: str
    column_rank: str
    card_rank: str
    hidden_at: datetime | None


@dataclass(frozen=True)
class PointsRow:
    points: int
    source: str
    updated_at: datetime


@dataclass(frozen=True)
class AtcRows:
    columns: list[ColumnDef]
    projects: dict[UUID, ProjectRow]
    modules: dict[UUID, ModuleRow]
    points: dict[UUID, PointsRow]


def load_rows(conn: psycopg.Connection) -> AtcRows:
    """Every ATC row, hidden ones included (the board treats a hidden row as no row)."""
    columns = [
        ColumnDef(*r)
        for r in conn.execute("SELECT key, label, position, priority FROM atc.column_def ORDER BY position")
    ]
    projects = {
        r[0]: ProjectRow(*r)
        for r in conn.execute(
            "SELECT plane_id, column_key, rank, repo, deploys, deploy_action, bau_enabled, hidden_at"
            " FROM atc.project"
        )
    }
    modules = {
        r[0]: ModuleRow(*r)
        for r in conn.execute(
            "SELECT id, project_id, unsorted, column_key, column_rank, card_rank, hidden_at FROM atc.module"
        )
    }
    points = {
        r[0]: PointsRow(*r[1:])
        for r in conn.execute("SELECT plane_id, points, points_source, updated_at FROM atc.work_item")
    }
    return AtcRows(columns=columns, projects=projects, modules=modules, points=points)


# --- Writers. Rows are created lazily: the first move of a project or module inserts its row.
# A write clears hidden_at: the item is live in Plane (the caller found it in the snapshot).


def put_project_placement(conn: psycopg.Connection, plane_id: UUID, column_key: str, rank: str) -> None:
    """Upsert a project's column and rank, leaving its metadata alone."""
    conn.execute(
        "INSERT INTO atc.project (plane_id, column_key, rank) VALUES (%s, %s, %s)"
        " ON CONFLICT (plane_id) DO UPDATE SET column_key = excluded.column_key, rank = excluded.rank,"
        " hidden_at = NULL, updated_at = now()",
        (plane_id, column_key, rank),
    )


def put_module_placement(
    conn: psycopg.Connection,
    module_id: UUID,
    project_id: UUID,
    *,
    unsorted: bool,
    column_key: str,
    column_rank: str,
    card_rank: str,
) -> None:
    """Upsert a module's (or Unsorted group's) column and both ranks."""
    conn.execute(
        "INSERT INTO atc.module (id, project_id, unsorted, column_key, column_rank, card_rank)"
        " VALUES (%s, %s, %s, %s, %s, %s)"
        " ON CONFLICT (id) DO UPDATE SET column_key = excluded.column_key,"
        " column_rank = excluded.column_rank, card_rank = excluded.card_rank,"
        " hidden_at = NULL, updated_at = now()",
        (module_id, project_id, unsorted, column_key, column_rank, card_rank),
    )


# --- Points and project metadata.


class AlreadySet(Exception):
    """`if_unestimated` was asked for but the item already has points."""


def set_points(
    conn: psycopg.Connection, item_id: UUID, points: int, source: str, *, if_unestimated: bool
) -> PointsRow:
    """Set an item's points. With `if_unestimated` an existing value is never touched (AlreadySet).

    The guard is one INSERT ... ON CONFLICT DO NOTHING, so it holds even without the move lock.
    """
    conflict = (
        "DO NOTHING"
        if if_unestimated
        else "DO UPDATE SET points = excluded.points, points_source = excluded.points_source,"
        " updated_at = now()"
    )
    row = conn.execute(
        "INSERT INTO atc.work_item (plane_id, points, points_source) VALUES (%s, %s, %s)"
        f" ON CONFLICT (plane_id) {conflict} RETURNING points, points_source, updated_at",
        (item_id, points, source),
    ).fetchone()
    if row is None:
        raise AlreadySet(str(item_id))
    return PointsRow(*row)


def _backlog_bottom_rank(conn: psycopg.Connection) -> str:
    row = conn.execute(
        "SELECT max(r) FROM ("
        " SELECT rank AS r FROM atc.project WHERE column_key = 'backlog' AND hidden_at IS NULL"
        " UNION ALL"
        " SELECT column_rank FROM atc.module WHERE column_key = 'backlog' AND hidden_at IS NULL"
        ") ranked"
    ).fetchone()
    return ranks.after(row[0])


def update_project_meta(
    conn: psycopg.Connection, project_id: UUID, *, rank: str | None = None, **fields
) -> ProjectRow:
    """Merge `fields` (repo, deploys, deploy_action, bau_enabled) into a project's row.

    A missing row is created in Backlog at `rank` (default: after every ranked Backlog card). A hidden
    row is revived from defaults: hidden means no row, so its stale metadata must not come back.
    """
    unknown = set(fields) - {"repo", "deploys", "deploy_action", "bau_enabled"}
    if unknown:
        raise TypeError(f"unknown project metadata {sorted(unknown)}")
    current = conn.execute(
        "SELECT column_key, rank, repo, deploys, deploy_action, bau_enabled, hidden_at"
        " FROM atc.project WHERE plane_id = %s FOR UPDATE",
        (project_id,),
    ).fetchone()
    if current is None or current[6] is not None:
        merged = {"column_key": "backlog", "rank": rank or _backlog_bottom_rank(conn), "repo": None,
                  "deploys": False, "deploy_action": "", "bau_enabled": False}  # fmt: skip
    else:
        keys = ("column_key", "rank", "repo", "deploys", "deploy_action", "bau_enabled")
        merged = dict(zip(keys, current[:6], strict=True))
    merged.update(fields)
    row = conn.execute(
        "INSERT INTO atc.project (plane_id, column_key, rank, repo, deploys, deploy_action, bau_enabled)"
        " VALUES (%(id)s, %(column_key)s, %(rank)s, %(repo)s, %(deploys)s, %(deploy_action)s,"
        " %(bau_enabled)s)"
        " ON CONFLICT (plane_id) DO UPDATE SET column_key = excluded.column_key, rank = excluded.rank,"
        " repo = excluded.repo, deploys = excluded.deploys, deploy_action = excluded.deploy_action,"
        " bau_enabled = excluded.bau_enabled, hidden_at = NULL, updated_at = now()"
        " RETURNING plane_id, column_key, rank, repo, deploys, deploy_action, bau_enabled, hidden_at",
        {"id": project_id, **merged},
    ).fetchone()
    return ProjectRow(*row)
