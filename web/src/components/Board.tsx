import {
  type CollisionDetection,
  closestCenter,
  DndContext,
  type DragEndEvent,
  KeyboardSensor,
  PointerSensor,
  pointerWithin,
  useSensor,
  useSensors,
} from '@dnd-kit/core';
import { sortableKeyboardCoordinates } from '@dnd-kit/sortable';
import { type BoardActions, useActions } from '../actions';
import { type DragRef, type DropRef, dropToRequest } from '../drag';
import type { Board as BoardData } from '../types';
import { Column } from './Column';

// Most specific first: a module row, then a card, then a column's empty space.
const specificity = (id: string) => (id.startsWith('row:') ? 0 : id.startsWith('card:') ? 1 : 2);

/**
 * Cards only land on cards and columns; module rows may also land on other module rows. Under the
 * pointer, the innermost target wins; with the keyboard (no pointer), the nearest one does.
 */
export const collide: CollisionDetection = (args) => {
  const ref = args.active.data.current?.ref as DragRef | undefined;
  const nested = ref?.projectId !== undefined;
  const droppableContainers = args.droppableContainers.filter(
    (c) => nested || !String(c.id).startsWith('row:'),
  );
  const hits = pointerWithin({ ...args, droppableContainers });
  if (hits.length > 0) {
    return [...hits].sort((a, b) => specificity(String(a.id)) - specificity(String(b.id)));
  }
  return closestCenter({ ...args, droppableContainers });
};

/** dnd-kit's onDragEnd: the finished drag becomes one move or reorder, or nothing. */
export function dragEndHandler(
  board: BoardData,
  actions: Pick<BoardActions, 'onMove' | 'onReorder'>,
) {
  return ({ active, over }: DragEndEvent) => {
    const ref = active.data.current?.ref as DragRef | undefined;
    const drop = over?.data.current?.drop as DropRef | undefined;
    if (!ref || !drop) return;
    const req = dropToRequest(ref, drop, board);
    if (req === null) return;
    if ('kind' in req) actions.onMove(req);
    else actions.onReorder(req);
  };
}

export function Board({ board }: { board: BoardData }) {
  const actions = useActions();
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={collide}
      onDragEnd={dragEndHandler(board, actions)}
    >
      <div
        className="grid grid-cols-1 items-start gap-3 md:[grid-template-columns:repeat(var(--cols),minmax(0,1fr))]"
        style={{ '--cols': board.columns.length } as React.CSSProperties}
      >
        {board.columns.map((c) => (
          <Column key={c.key} column={c} />
        ))}
      </div>
    </DndContext>
  );
}
