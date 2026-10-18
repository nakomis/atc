"""ATC's own rows in schema `atc`: columns, project and module placement, and points."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import psycopg


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
