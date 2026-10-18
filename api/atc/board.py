"""The board read model: Plane's projects, modules and open items laid out in ATC's columns.

Spec §5 and §11. A project or module with no ATC row (or a hidden one) sits in Backlog after
the ranked cards, by Plane `created_at`. Each open item belongs to exactly one module: the
first open module it is in, in priority order, else its project's synthetic Unsorted group.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid5

from atc.plane import PlaneItem, PlaneProject, PlaneSnapshot
from atc.store import AtcRows

# Fixed for ever: Unsorted ids derive from it, and atc.module rows are keyed by them.
UNSORTED_NAMESPACE = UUID("6a1f0c3e-5b7d-4e2a-9c84-41544355e500")
UNSORTED_NAME = "Unsorted"
DEFAULT_COLUMN = "backlog"
CLOSED_MODULE_STATUSES = frozenset({"completed", "cancelled"})
PRIORITY_RANK = {"urgent": 0, "high": 1, "medium": 2, "low": 3, "none": 4}

# Sort key for cards and modules: ranked first (by rank, bytewise like COLLATE "C"), then
# rowless by Plane created_at; the id breaks any remaining tie so the order is total.
type SortKey = tuple[int, str, datetime, str]


def unsorted_id(project_id: UUID) -> UUID:
    """The stable id of a project's synthetic Unsorted group."""
    return uuid5(UNSORTED_NAMESPACE, str(project_id))


@dataclass
class ItemView:
    id: UUID
    ref: str
    name: str
    state: str
    state_group: str
    priority: str
    points: int | None
    points_source: str | None
    url: str
    project_id: UUID = field(repr=False)
    order: tuple = field(repr=False, default=())  # (sort_order, priority rank, created_at, sequence_id)

    def to_json(self) -> dict:
        return {
            "id": str(self.id),
            "ref": self.ref,
            "name": self.name,
            "state": self.state,
            "state_group": self.state_group,
            "priority": self.priority,
            "points": self.points,
            "points_source": self.points_source,
            "url": self.url,
        }


@dataclass
class ModuleView:
    id: UUID
    project_id: UUID
    name: str
    unsorted: bool
    status: str | None
    column_key: str
    items: list[ItemView] = field(default_factory=list)

    @property
    def open(self) -> bool:
        return self.status not in CLOSED_MODULE_STATUSES

    @property
    def points(self) -> int:
        return sum(i.points or 0 for i in self.items)

    @property
    def unestimated(self) -> int:
        return sum(1 for i in self.items if i.points is None)

    def to_json(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "unsorted": self.unsorted,
            "status": self.status,
            "points": self.points,
            "unestimated": self.unestimated,
            "items": [i.to_json() for i in self.items],
        }


@dataclass
class Card:
    kind: str  # "project" | "module"
    id: UUID
    project_id: UUID
    identifier: str
    label: str
    modules: list[ModuleView] = field(default_factory=list)

    @property
    def points(self) -> int:
        return sum(m.points for m in self.modules)

    @property
    def unestimated(self) -> int:
        return sum(m.unestimated for m in self.modules)

    def to_json(self) -> dict:
        return {
            "kind": self.kind,
            "id": str(self.id),
            "project_id": str(self.project_id),
            "identifier": self.identifier,
            "label": self.label,
            "points": self.points,
            "unestimated": self.unestimated,
            "modules": [m.to_json() for m in self.modules],
        }


@dataclass
class Column:
    key: str
    label: str
    priority: int
    cards: list[Card] = field(default_factory=list)

    @property
    def points(self) -> int:
        return sum(c.points for c in self.cards)

    @property
    def unestimated(self) -> int:
        return sum(c.unestimated for c in self.cards)

    def to_json(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "points": self.points,
            "unestimated": self.unestimated,
            "cards": [c.to_json() for c in self.cards],
        }


@dataclass
class Board:
    columns: list[Column]  # display order
    projects: dict[UUID, PlaneProject]
    max_points: int
    generated_at: datetime

    def to_json(self) -> dict:
        return {
            "columns": [c.to_json() for c in self.columns],
            "max_points": self.max_points,
            "generated_at": self.generated_at.isoformat(),
        }


def priority_modules(board: Board) -> list[ModuleView]:
    """Every module on the board in priority order: columns by priority, then cards, then card order."""
    return [
        m
        for column in sorted(board.columns, key=lambda c: c.priority)
        for card in column.cards
        for m in card.modules
    ]


def _key(rank: str | None, created_at: datetime, ident: UUID, rowless_tier: int = 1) -> SortKey:
    if rank is not None:
        return (0, rank, created_at, str(ident))
    return (rowless_tier, "", created_at, str(ident))


def _item_order(item: PlaneItem) -> tuple:
    return (
        item.sort_order,
        PRIORITY_RANK.get(item.priority, len(PRIORITY_RANK)),
        item.created_at,
        item.sequence_id,
    )


def build_board(
    snap: PlaneSnapshot,
    rows: AtcRows,
    *,
    include_all: bool,
    link: Callable[[str], str],
    max_points: int = 100,
) -> Board:
    """Lay the snapshot out in ATC's columns; collapse closed and empty groups unless `include_all`.

    `snap` must be consistent (as `read_plane` returns it): every module and item belongs to
    one of its projects.
    """
    column_keys = {c.key for c in rows.columns}
    projects = {p.id: p for p in snap.projects}
    live_projects = {pid: r for pid, r in rows.projects.items() if r.hidden_at is None}
    live_modules = {mid: r for mid, r in rows.modules.items() if r.hidden_at is None}

    def placed(column_key: str | None) -> str:
        return column_key if column_key in column_keys else DEFAULT_COLUMN

    project_column: dict[UUID, str] = {}
    project_key: dict[UUID, SortKey] = {}
    for p in snap.projects:
        row = live_projects.get(p.id)
        project_column[p.id] = placed(row.column_key if row else None)
        project_key[p.id] = _key(row.rank if row else None, p.created_at, p.id)

    # Every module, closed ones too, with its column and its two sort keys.
    modules: list[tuple[ModuleView, SortKey, SortKey]] = []
    for m in snap.modules:
        row = live_modules.get(m.id)
        view = ModuleView(
            m.id, m.project_id, m.name, False, m.status, placed(row.column_key if row else None)
        )
        modules.append(
            (
                view,
                _key(row.column_rank if row else None, m.created_at, m.id),
                _key(row.card_rank if row else None, m.created_at, m.id),
            )
        )
    for p in snap.projects:
        uid = unsorted_id(p.id)
        row = live_modules.get(uid)
        # A rowless Unsorted takes its project's column and sits after the rowless modules.
        column = placed(row.column_key) if row else project_column[p.id]
        view = ModuleView(uid, p.id, UNSORTED_NAME, True, None, column)
        modules.append(
            (
                view,
                _key(row.column_rank if row else None, p.created_at, uid, rowless_tier=2),
                _key(row.card_rank if row else None, p.created_at, uid, rowless_tier=2),
            )
        )

    by_project: dict[UUID, list[tuple[SortKey, ModuleView]]] = {}
    keyed_cards: dict[str, list[tuple[SortKey, Card]]] = {c.key: [] for c in rows.columns}
    for view, column_key, card_key in modules:
        p = projects[view.project_id]
        if view.column_key == project_column[p.id]:
            by_project.setdefault(p.id, []).append((card_key, view))
        else:
            card = Card("module", view.id, p.id, p.identifier, f"{p.identifier} · {view.name}", [view])
            keyed_cards[view.column_key].append((column_key, card))
    for p in snap.projects:
        card_modules = [v for _, v in sorted(by_project.get(p.id, []), key=lambda kv: kv[0])]
        card = Card("project", p.id, p.id, p.identifier, p.name, card_modules)
        keyed_cards[project_column[p.id]].append((project_key[p.id], card))

    columns = [
        Column(
            c.key, c.label, c.priority, [card for _, card in sorted(keyed_cards[c.key], key=lambda kv: kv[0])]
        )
        for c in rows.columns
    ]
    board = Board(columns, projects, max_points, datetime.now(UTC))

    # Assign each open item to the first open module it belongs to, in priority order.
    position = {m.id: n for n, m in enumerate(priority_modules(board)) if m.open}
    unsorted = {m.project_id: m for m in priority_modules(board) if m.unsorted}
    views = {m.id: m for m in priority_modules(board)}
    for item in snap.items:
        candidates = [mid for mid in item.module_ids if mid in position]
        target = views[min(candidates, key=position.__getitem__)] if candidates else unsorted[item.project_id]
        pts = rows.points.get(item.id)
        target.items.append(
            ItemView(
                item.id,
                item.ref,
                item.name,
                item.state,
                item.state_group,
                item.priority,
                pts.points if pts else None,
                pts.source if pts else None,
                link(item.ref),
                project_id=item.project_id,
                order=_item_order(item),
            )
        )
    for view in views.values():
        view.items.sort(key=lambda i: i.order)

    if not include_all:
        _collapse(board, {i.project_id for i in snap.items})
    return board


def _collapse(board: Board, busy_projects: set[UUID]) -> None:
    """Drop modules with no open items (closed ones never get any) and projects with none at all.

    The brief lists closed modules and empty Unsorted groups; its Review Focus 4 test also
    expects an open module left empty by a removed membership to go, so any empty module goes.
    """

    def shown(m: ModuleView) -> bool:
        return m.open and bool(m.items)

    for column in board.columns:
        kept = []
        for card in column.cards:
            if card.project_id not in busy_projects:
                continue
            card.modules = [m for m in card.modules if shown(m)]
            if card.kind == "project" or card.modules:
                kept.append(card)
        column.cards = kept
