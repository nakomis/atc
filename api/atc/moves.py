"""Moves and reorders on the board (spec §5): each writes ATC rows for one drag.

Placement is worked out on the full board (`include_all`), so cards and modules collapsed out of
the default view keep their places. Rowless cards sort after ranked ones, so placing something
after a rowless card first gives ranks to the rowless cards ahead of it (lazy rows); otherwise a
drag writes only the row it moves.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal
from uuid import UUID

import psycopg

from atc import ranks, store
from atc.board import DEFAULT_COLUMN, Board, Card, ModuleView, build_board, priority_modules
from atc.plane import PlaneSnapshot
from atc.store import AtcRows


class NotFound(LookupError):
    """The project or module is not on the board (unknown, deleted or archived in Plane)."""


class Invalid(ValueError):
    """The request names a column, card or module that does not fit the move."""


def place[K](entries: Sequence[tuple[K, str | None]], index: int) -> tuple[str, list[tuple[K, str]]]:
    """A rank for a new entry at `index` in `entries` (ordered, ranked ones first, rank None = rowless).

    Returns the new rank and `(key, rank)` for each existing entry that must be (re)ranked too:
    the rowless entries ahead of `index`, or all of them if neighbouring ranks have collided or a
    key would grow past `ranks.REBALANCE_LENGTH` (so repeated drops at one end stay cheap).
    """
    if not 0 <= index <= len(entries):
        raise IndexError(index)
    ranked = next((n for n, (_, r) in enumerate(entries) if r is None), len(entries))
    try:
        if index <= ranked:
            lo = entries[index - 1][1] if index else None
            hi = entries[index][1] if index < ranked else None
            rank, filled = ranks.between(lo, hi), []
        else:
            last = entries[ranked - 1][1] if ranked else None
            filled = []
            for key, _ in entries[ranked:index]:
                last = ranks.after(last)
                filled.append((key, last))
            rank = ranks.after(last)
    except ValueError:  # two neighbours share a rank (a race); rank the whole list afresh
        return _rerank(entries, index)
    if len(rank) > ranks.REBALANCE_LENGTH or any(len(r) > ranks.REBALANCE_LENGTH for _, r in filled):
        return _rerank(entries, index)
    return rank, filled


def _rerank[K](entries: Sequence[tuple[K, str | None]], index: int) -> tuple[str, list[tuple[K, str]]]:
    keys = [k for k, _ in entries]
    fresh = ranks.spread(len(keys) + 1)
    return fresh[index], list(zip(keys, fresh[:index] + fresh[index + 1 :], strict=True))


class _Layout:
    """The full board plus the ATC rows behind it, and the writes that keep the two in step."""

    def __init__(self, conn: psycopg.Connection, snap: PlaneSnapshot, rows: AtcRows) -> None:
        self.conn = conn
        self.board: Board = build_board(snap, rows, include_all=True, link=str)
        self.projects = {pid: r for pid, r in rows.projects.items() if r.hidden_at is None}
        self.module_rows = {mid: r for mid, r in rows.modules.items() if r.hidden_at is None}
        self.modules: dict[UUID, ModuleView] = {m.id: m for m in priority_modules(self.board)}
        self.project_cards: dict[UUID, tuple[str, Card]] = {
            card.id: (column.key, card)
            for column in self.board.columns
            for card in column.cards
            if card.kind == "project"
        }

    def cards(self, column_key: str) -> list[Card]:
        for column in self.board.columns:
            if column.key == column_key:
                return column.cards
        raise Invalid(f"unknown column {column_key!r}")

    def column_rank(self, card: Card) -> str | None:
        if card.kind == "project":
            row = self.projects.get(card.id)
            return row.rank if row else None
        row = self.module_rows.get(card.id)
        return row.column_rank if row else None

    def card_rank(self, view: ModuleView) -> str | None:
        row = self.module_rows.get(view.id)
        return row.card_rank if row else None

    def write_project(self, project_id: UUID, column_key: str, rank: str) -> None:
        store.put_project_placement(self.conn, project_id, column_key, rank)

    def write_module(
        self,
        view: ModuleView,
        column_key: str,
        *,
        column_rank: str | None = None,
        card_rank: str | None = None,
    ) -> None:
        """Write one module row; a rank not given keeps its current value (or, rowless, takes the other).

        Only one of the two ranks is in force at a time (column_rank on a module card, card_rank
        inside its project card), and every move into the other role sets that rank afresh.
        """
        row = self.module_rows.get(view.id)
        column_rank = column_rank or (row.column_rank if row else card_rank)
        card_rank = card_rank or (row.card_rank if row else column_rank)
        assert column_rank and card_rank
        store.put_module_placement(
            self.conn,
            view.id,
            view.project_id,
            unsorted=view.unsorted,
            column_key=column_key,
            column_rank=column_rank,
            card_rank=card_rank,
        )

    def write_card(self, card: Card, column_key: str, rank: str) -> None:
        if card.kind == "project":
            self.write_project(card.id, column_key, rank)
        else:
            self.write_module(card.modules[0], column_key, column_rank=rank)

    def place_card(self, column_key: str, cards: list[Card], index: int) -> str:
        """Rank for a card at `index` among `cards` of `column_key`, ranking rowless cards ahead of it."""
        rank, filled = place([(c, self.column_rank(c)) for c in cards], index)
        for card, r in filled:
            self.write_card(card, column_key, r)
        return rank

    def place_in_card(self, column_key: str, views: list[ModuleView], index: int) -> str:
        """Rank for a module at `index` among `views` in a project card, ranking rowless ones ahead."""
        rank, filled = place([(v, self.card_rank(v)) for v in views], index)
        for view, r in filled:
            self.write_module(view, column_key, card_rank=r)
        return rank


def _index(ids: list[UUID], before_id: UUID | None) -> int:
    return len(ids) if before_id is None else ids.index(before_id)


def move(
    conn: psycopg.Connection,
    snap: PlaneSnapshot,
    rows: AtcRows,
    *,
    kind: Literal["project", "module"],
    id: UUID,
    to_column: str,
    before_id: UUID | None,
) -> None:
    """Move a project or module card to `to_column`, before the card `before_id` or at the bottom."""
    layout = _Layout(conn, snap, rows)
    if kind == "project" and id not in layout.project_cards:
        raise NotFound(f"no project {id}")
    if kind == "module" and id not in layout.modules:
        raise NotFound(f"no module {id}")
    cards = layout.cards(to_column)
    if before_id is not None and (before_id == id or before_id not in {c.id for c in cards}):
        raise Invalid(f"{before_id} is not another card in {to_column!r}")
    if kind == "project":
        _move_project(layout, id, to_column, cards, before_id)
    else:
        _move_module(layout, layout.modules[id], to_column, cards, before_id)


def _move_project(
    layout: _Layout, project_id: UUID, to: str, cards: list[Card], before_id: UUID | None
) -> None:
    source, card = layout.project_cards[project_id]
    if source == to:  # a reorder of the card within its column
        others = [c for c in cards if c.id != project_id]
        rank = layout.place_card(to, others, _index([c.id for c in others], before_id))
        layout.write_project(project_id, to, rank)
        return
    # The project's module cards in the target column fold into its card.
    absorbed = [c for c in cards if c.kind == "module" and c.project_id == project_id]
    gone = {c.id for c in absorbed}
    remaining = [c for c in cards if c.id not in gone]
    stop = _index([c.id for c in cards], before_id)
    index = sum(1 for c in cards[:stop] if c.id not in gone)
    layout.write_project(project_id, to, layout.place_card(to, remaining, index))
    # Modules already in the target first, in their order there, then those from the source card.
    rank: str | None = None
    for view in [c.modules[0] for c in absorbed] + card.modules:
        rank = ranks.after(rank)
        layout.write_module(view, to, card_rank=rank)


def _move_module(
    layout: _Layout, view: ModuleView, to: str, cards: list[Card], before_id: UUID | None
) -> None:
    project_column, card = layout.project_cards[view.project_id]
    if to == project_column:
        if view.column_key == to:  # already in its project card: nothing to do
            return
        layout.write_module(view, to, card_rank=layout.place_in_card(to, card.modules, len(card.modules)))
        return
    others = [c for c in cards if c.id != view.id]
    rank = layout.place_card(to, others, _index([c.id for c in others], before_id))
    layout.write_module(view, to, column_rank=rank)


def reorder(
    conn: psycopg.Connection,
    snap: PlaneSnapshot,
    rows: AtcRows,
    *,
    project_id: UUID,
    module_id: UUID,
    before_id: UUID | None,
) -> None:
    """Move a module within its project card, before module `before_id` or to the bottom."""
    layout = _Layout(conn, snap, rows)
    if project_id not in layout.project_cards:
        raise NotFound(f"no project {project_id}")
    if module_id not in layout.modules:
        raise NotFound(f"no module {module_id}")
    column_key, card = layout.project_cards[project_id]
    if module_id not in {m.id for m in card.modules}:
        raise Invalid(f"module {module_id} is not in the card of project {project_id}")
    others = [m for m in card.modules if m.id != module_id]
    if before_id is not None and before_id not in {m.id for m in others}:
        raise Invalid(f"{before_id} is not another module in the card")
    rank = layout.place_in_card(column_key, others, _index([m.id for m in others], before_id))
    layout.write_module(layout.modules[module_id], column_key, card_rank=rank)


def backlog_rank_in_place(
    conn: psycopg.Connection, snap: PlaneSnapshot, rows: AtcRows, project_id: UUID
) -> str:
    """Rank that keeps a rowless project's card exactly where it sits in Backlog now.

    Rowless cards sort after ranked ones, so those ahead of it are given ranks first (lazy rows).
    """
    layout = _Layout(conn, snap, rows)
    if project_id not in layout.project_cards:
        raise NotFound(f"no project {project_id}")
    cards = layout.cards(DEFAULT_COLUMN)
    index = [c.id for c in cards].index(project_id)
    return layout.place_card(DEFAULT_COLUMN, [c for c in cards if c.id != project_id], index)


def rebalance_column(conn: psycopg.Connection, snap: PlaneSnapshot, column_key: str) -> int:
    """Give every ranked card in `column_key` a fresh, short, evenly spaced rank, keeping the order.

    Reconcile calls this (under the move lock) when its Backlog appends would pass
    `ranks.REBALANCE_LENGTH`. Rowless cards keep no rank: they already sort after every ranked one.
    Modules inside a project card carry a column rank that is not in force, but Backlog's tail
    (`store.backlog_max_rank`) reads it, so they take their card's new rank. Rows are read afresh,
    so rows written earlier in the same transaction are included. Returns the number of cards
    re-ranked.
    """
    layout = _Layout(conn, snap, store.load_rows(conn))
    ranked = [c for c in layout.cards(column_key) if layout.column_rank(c) is not None]
    for card, rank in zip(ranked, ranks.spread(len(ranked)), strict=True):
        layout.write_card(card, column_key, rank)
        if card.kind == "project":
            for view in card.modules:
                if view.id in layout.module_rows:
                    layout.write_module(view, column_key, column_rank=rank)
    return len(ranked)
