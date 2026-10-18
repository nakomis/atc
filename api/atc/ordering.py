"""Priority order over the board: what to work on next, the full priority list, and BAU's project order.

Spec §6 and §11. Order is columns by priority, then cards, then modules within a card, then items by
`(sort_order, priority rank, created_at, sequence_id)`; `board.priority_modules` and the item order
already encode it, so this module only walks the board.
"""

from __future__ import annotations

from uuid import UUID

from atc.board import DEFAULT_COLUMN, Board, ItemView, ModuleView, priority_modules
from atc.plane import PlaneSnapshot
from atc.store import AtcRows

NEXT_COLUMNS = ("in_progress", "next")
NEXT_COUNT = 3  # the next item plus two runners-up


def _walk(board: Board, column_key: str | None = None):
    """(module, item) pairs in priority order, optionally within one column."""
    columns = sorted(board.columns, key=lambda c: c.priority)
    for column in columns:
        if column_key is not None and column.key != column_key:
            continue
        for card in column.cards:
            for module in card.modules:
                for item in module.items:
                    yield module, item


def _next_item(board: Board, module: ModuleView, item: ItemView) -> dict:
    project = board.projects[module.project_id]
    return {
        "id": str(item.id),
        "ref": item.ref,
        "name": item.name,
        "points": item.points,
        "url": item.url,
        "module": {"id": str(module.id), "name": module.name, "unsorted": module.unsorted},
        "project": {"id": str(project.id), "identifier": project.identifier, "name": project.name},
    }


def next_items(board: Board) -> tuple[str | None, list[dict]]:
    """The column the next item comes from and up to three items: In progress, else Up next, else none.

    Runners-up continue the same walk, so may cross modules and projects but never columns.
    """
    for key in NEXT_COLUMNS:
        found = [_next_item(board, m, i) for m, i in _walk(board, key)][:NEXT_COUNT]
        if found:
            return key, found
    return None, []


def priority_refs(board: Board) -> list[str]:
    """Every open item's ref in priority order."""
    return [item.ref for module in priority_modules(board) for item in module.items]


def projects_in_priority(board: Board, snap: PlaneSnapshot, rows: AtcRows) -> list[UUID]:
    """Each project at its first appearance in priority order; projects off the board follow by identifier."""
    seen: dict[UUID, None] = {}
    for module in priority_modules(board):
        seen.setdefault(module.project_id)
    rest = sorted((p for p in snap.projects if p.id not in seen), key=lambda p: (p.identifier, str(p.id)))
    return [*seen, *(p.id for p in rest)]


def project_meta(board_projects, rows: AtcRows, project_id: UUID, columns: set[str]) -> dict:
    """ProjectMeta for one project.

    One rule for every field: a hidden ATC row is no row. A missing or hidden row means Backlog with
    default metadata (no repo, no deploys, BAU off), matching how the board treats it. Reads only:
    reconcile (or a PUT) unhides the row, and then its old column and metadata return.
    """
    project = board_projects[project_id]
    row = rows.projects.get(project_id)
    live = row if row is not None and row.hidden_at is None else None
    column = live.column_key if live and live.column_key in columns else DEFAULT_COLUMN
    return {
        "id": str(project.id),
        "identifier": project.identifier,
        "name": project.name,
        "column": column,
        "repo": live.repo if live else None,
        "deploys": live.deploys if live else False,
        "deploy_action": live.deploy_action if live else "",
        "bau_enabled": live.bau_enabled if live else False,
    }
