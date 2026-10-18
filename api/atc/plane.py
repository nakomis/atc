"""Read-only access to Plane's tables: the live projects, modules and open work items of one workspace."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import psycopg

# Every Plane table and column ATC reads (verified against Plane v1.4.2 and the live database).
_COMMON = frozenset({"id", "created_at", "deleted_at"})
REQUIRED_COLUMNS: dict[str, frozenset[str]] = {
    "workspaces": _COMMON | {"slug"},
    "projects": _COMMON | {"workspace_id", "identifier", "name", "archived_at"},
    "modules": _COMMON | {"project_id", "name", "status", "sort_order", "archived_at"},
    "module_issues": _COMMON | {"module_id", "issue_id"},
    "issues": _COMMON
    | {
        "project_id",
        "sequence_id",
        "name",
        "state_id",
        "priority",
        "sort_order",
        "parent_id",
        "description_stripped",
        "archived_at",
        "is_draft",
    },
    "states": _COMMON | {"project_id", "name", "group"},
}

CLOSED_GROUPS = ("completed", "cancelled")


@dataclass(frozen=True)
class PlaneProject:
    id: UUID
    identifier: str
    name: str
    created_at: datetime


@dataclass(frozen=True)
class PlaneModule:
    id: UUID
    project_id: UUID
    name: str
    status: str
    created_at: datetime


@dataclass(frozen=True)
class PlaneItem:
    id: UUID
    project_id: UUID
    ref: str
    name: str
    state: str
    state_group: str
    priority: str
    sort_order: float
    created_at: datetime
    sequence_id: int
    module_ids: tuple[UUID, ...]


@dataclass(frozen=True)
class PlaneSnapshot:
    projects: list[PlaneProject]
    modules: list[PlaneModule]
    items: list[PlaneItem]


# Live, unarchived projects of the workspace; every query below joins through this.
_LIVE_PROJECTS = """
    SELECT p.id, p.identifier, p.name, p.created_at
    FROM public.projects p
    JOIN public.workspaces w ON w.id = p.workspace_id AND w.deleted_at IS NULL
    WHERE w.slug = %(slug)s AND p.deleted_at IS NULL AND p.archived_at IS NULL
"""

_MODULES = f"""
    WITH lp AS ({_LIVE_PROJECTS})
    SELECT m.id, m.project_id, m.name, m.status, m.created_at
    FROM public.modules m
    JOIN lp ON lp.id = m.project_id
    WHERE m.deleted_at IS NULL AND m.archived_at IS NULL
    ORDER BY m.created_at, m.id
"""

# Open = state group not completed/cancelled, and the item not deleted, archived or a draft.
# Memberships come from live module_issues rows only: Plane soft-deletes them on removal.
_ITEMS = f"""
    WITH lp AS ({_LIVE_PROJECTS})
    SELECT i.id, i.project_id, lp.identifier || '-' || i.sequence_id, i.name, s.name, s."group",
           i.priority, i.sort_order, i.created_at, i.sequence_id,
           array(
               SELECT mi.module_id FROM public.module_issues mi
               WHERE mi.issue_id = i.id AND mi.deleted_at IS NULL
               ORDER BY mi.created_at, mi.module_id
           )
    FROM public.issues i
    JOIN lp ON lp.id = i.project_id
    JOIN public.states s ON s.id = i.state_id AND s.deleted_at IS NULL
    WHERE i.deleted_at IS NULL AND i.archived_at IS NULL AND NOT i.is_draft
      AND s."group" <> ALL(%(closed)s)
    ORDER BY i.project_id, i.sequence_id
"""


def read_plane(conn: psycopg.Connection, workspace_slug: str) -> PlaneSnapshot:
    """The workspace's live projects, live modules (all statuses) and open items."""
    args = {"slug": workspace_slug, "closed": list(CLOSED_GROUPS)}
    projects = [
        PlaneProject(*row) for row in conn.execute(_LIVE_PROJECTS + " ORDER BY p.created_at, p.id", args)
    ]
    modules = [PlaneModule(*row) for row in conn.execute(_MODULES, args)]
    items = [PlaneItem(*row[:10], module_ids=tuple(row[10])) for row in conn.execute(_ITEMS, args).fetchall()]
    return PlaneSnapshot(projects=projects, modules=modules, items=items)


def missing_columns(conn: psycopg.Connection) -> list[str]:
    """`table.column` for each required Plane column the current role cannot see, sorted.

    information_schema.columns lists only columns the role holds a privilege on, so a lost
    grant shows up here as well as a renamed or dropped column.
    """
    rows = conn.execute(
        "SELECT table_name, column_name FROM information_schema.columns"
        " WHERE table_schema = 'public' AND table_name = ANY(%s)",
        (list(REQUIRED_COLUMNS),),
    ).fetchall()
    seen = {(t, c) for t, c in rows}
    return sorted(
        f"{table}.{column}"
        for table, columns in REQUIRED_COLUMNS.items()
        for column in columns
        if (table, column) not in seen
    )
