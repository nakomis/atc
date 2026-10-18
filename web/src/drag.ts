import type { Board, Card, MoveRequest, ReorderRequest } from './types';

/**
 * What is being dragged: a card (project or single module), or a module row inside a project card
 * (then `projectId` names the card it sits in).
 */
export interface DragRef {
  kind: 'project' | 'module';
  id: string;
  projectId?: string;
}

/** Where it was dropped: a module row, a card, or the empty part of a column. */
export type DropRef =
  | { moduleId: string; projectId: string }
  | { cardId: string; column: string }
  | { column: string };

interface Located {
  column: string;
  index: number;
  card: Card;
}

function findCard(board: Board, pred: (c: Card) => boolean): Located | null {
  for (const col of board.columns) {
    const index = col.cards.findIndex(pred);
    if (index >= 0) return { column: col.key, index, card: col.cards[index] };
  }
  return null;
}

const cardById = (board: Board, id: string) => findCard(board, (c) => c.id === id);
const projectCardHolding = (board: Board, moduleId: string) =>
  findCard(board, (c) => c.kind === 'project' && c.modules.some((m) => m.id === moduleId));

/**
 * The id to place `active` before when it is dropped on `over` in the same list. Dragging down
 * lands after the target (as dnd-kit's sortable preview shows it), dragging up lands before it.
 */
function beforeInList(ids: string[], active: string, over: string): string | null {
  const from = ids.indexOf(active);
  const to = ids.indexOf(over);
  if (from >= 0 && from < to) return ids[to + 1] ?? null;
  return over;
}

/** Turn a finished drag into the API call it means, or null when nothing would change. Pure. */
export function dropToRequest(
  active: DragRef,
  over: DropRef,
  board: Board,
): MoveRequest | ReorderRequest | null {
  const nested = active.kind === 'module' && active.projectId !== undefined;
  const move = (to_column: string, before_id: string | null): MoveRequest => ({
    kind: active.kind,
    id: active.id,
    to_column,
    before_id,
  });

  let target = over;
  if ('moduleId' in target) {
    const host = projectCardHolding(board, target.moduleId);
    if (host === null) return null;
    if (nested && host.card.id === active.projectId) {
      if (active.id === target.moduleId) return null;
      const ids = host.card.modules.map((m) => m.id);
      return {
        project_id: host.card.project_id,
        module_id: active.id,
        before_id: beforeInList(ids, active.id, target.moduleId),
      };
    }
    target = { cardId: host.card.id, column: host.column };
  }

  // A nested row's own position is its host card's.
  const source = nested ? cardById(board, active.projectId as string) : cardById(board, active.id);

  if ('cardId' in target) {
    if (target.cardId === active.id) return null;
    if (nested && target.cardId === active.projectId) return null;
    const column = board.columns.find((c) => c.key === target.column);
    if (!nested && source !== null && source.column === target.column && column) {
      const ids = column.cards.map((c) => c.id);
      return move(target.column, beforeInList(ids, active.id, target.cardId));
    }
    return move(target.column, target.cardId);
  }

  if (source !== null && source.column === target.column) {
    if (nested) return null;
    const column = board.columns.find((c) => c.key === target.column);
    if (column && source.index === column.cards.length - 1) return null;
  }
  return move(target.column, null);
}
