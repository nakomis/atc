"""Builds Plane rows in the test database, the way Plane itself would store them."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

import psycopg

PLANE_TABLES = (
    "workspaces",
    "projects",
    "states",
    "modules",
    "issues",
    "module_issues",
    "labels",
    "issue_labels",
)


class PlaneFactory:
    """Writes Plane's tables directly over an autocommit connection as the Plane owner."""

    def __init__(self, conn: psycopg.Connection) -> None:
        self.conn = conn
        self._workspace_id: UUID | None = None

    def workspace(self, slug: str = "nakomis") -> UUID:
        wid = uuid4()
        self.conn.execute("INSERT INTO public.workspaces (id, slug) VALUES (%s, %s)", (wid, slug))
        if self._workspace_id is None:
            self._workspace_id = wid
        return wid

    def project(self, identifier: str, name: str | None = None, archived: bool = False) -> UUID:
        if self._workspace_id is None:
            self.workspace()
        pid = uuid4()
        self.conn.execute(
            "INSERT INTO public.projects (id, workspace_id, identifier, name, archived_at)"
            " VALUES (%s, %s, %s, %s, CASE WHEN %s THEN now() END)",
            (pid, self._workspace_id, identifier, name or f"{identifier} project", archived),
        )
        return pid

    def state(self, project_id: UUID, group: str, name: str | None = None) -> UUID:
        sid = uuid4()
        self.conn.execute(
            'INSERT INTO public.states (id, project_id, name, "group") VALUES (%s, %s, %s, %s)',
            (sid, project_id, name or group.title(), group),
        )
        return sid

    def module(self, project_id: UUID, name: str, status: str = "planned") -> UUID:
        mid = uuid4()
        self.conn.execute(
            "INSERT INTO public.modules (id, project_id, name, status) VALUES (%s, %s, %s, %s)",
            (mid, project_id, name, status),
        )
        return mid

    def item(
        self,
        project_id: UUID,
        name: str,
        state_id: UUID,
        *,
        modules: tuple[UUID, ...] | list[UUID] = (),
        sort_order: float = 65535.0,
        priority: str = "none",
        created_at: datetime | None = None,
    ) -> UUID:
        iid = uuid4()
        # clock_timestamp() rather than now(): items made in one test get distinct, ordered times.
        self.conn.execute(
            "INSERT INTO public.issues"
            " (id, project_id, sequence_id, name, state_id, priority, sort_order, created_at)"
            " SELECT %s, %s, coalesce(max(sequence_id), 0) + 1, %s, %s, %s, %s,"
            "        coalesce(%s::timestamptz, clock_timestamp())"
            " FROM public.issues WHERE project_id = %s",
            (iid, project_id, name, state_id, priority, sort_order, created_at, project_id),
        )
        for module_id in modules:
            self.conn.execute(
                "INSERT INTO public.module_issues (id, module_id, issue_id) VALUES (%s, %s, %s)",
                (uuid4(), module_id, iid),
            )
        return iid

    def remove_from_module(self, item_id: UUID, module_id: UUID) -> None:
        """Plane soft-deletes the membership row rather than removing it."""
        self.conn.execute(
            "UPDATE public.module_issues SET deleted_at = now()"
            " WHERE issue_id = %s AND module_id = %s AND deleted_at IS NULL",
            (item_id, module_id),
        )

    def archive_project(self, project_id: UUID) -> None:
        self.conn.execute("UPDATE public.projects SET archived_at = now() WHERE id = %s", (project_id,))

    def unarchive_project(self, project_id: UUID) -> None:
        self.conn.execute("UPDATE public.projects SET archived_at = NULL WHERE id = %s", (project_id,))

    def delete_module(self, module_id: UUID) -> None:
        self.conn.execute("UPDATE public.modules SET deleted_at = now() WHERE id = %s", (module_id,))

    def ref(self, item_id: UUID) -> str:
        row = self.conn.execute(
            "SELECT p.identifier || '-' || i.sequence_id FROM public.issues i"
            " JOIN public.projects p ON p.id = i.project_id WHERE i.id = %s",
            (item_id,),
        ).fetchone()
        if row is None:
            raise KeyError(item_id)
        return row[0]

    def name(self, ref: str) -> str:
        identifier, _, sequence = ref.rpartition("-")
        row = self.conn.execute(
            "SELECT i.name FROM public.issues i JOIN public.projects p ON p.id = i.project_id"
            " WHERE p.identifier = %s AND i.sequence_id = %s",
            (identifier, int(sequence)),
        ).fetchone()
        if row is None:
            raise KeyError(ref)
        return row[0]
