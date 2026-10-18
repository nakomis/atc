import { useDroppable } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';
import type { DropRef } from '../drag';
import type { Column as ColumnData } from '../types';
import { Card } from './Card';

/** One ordered list of cards, with its points total in the header. */
export function Column({ column }: { column: ColumnData }) {
  const drop: DropRef = { column: column.key };
  const { setNodeRef, isOver } = useDroppable({ id: `col:${column.key}`, data: { drop } });
  return (
    <section
      ref={setNodeRef}
      aria-label={column.label}
      className={`flex min-h-40 flex-col rounded-lg p-2 ${isOver ? 'bg-sky-500/10' : 'bg-neutral-500/10'}`}
    >
      <header className="mb-2 flex items-baseline gap-2">
        <h2 className="font-semibold">
          {column.label} · {column.points} pts
        </h2>
        {column.unestimated > 0 && (
          <span className="text-xs text-amber-600 dark:text-amber-400">
            +{column.unestimated} unestimated
          </span>
        )}
      </header>
      <SortableContext
        items={column.cards.map((c) => `card:${c.id}`)}
        strategy={verticalListSortingStrategy}
      >
        <div className="flex flex-1 flex-col gap-2">
          {column.cards.map((card, i) => (
            <Card key={card.id} card={card} column={column} index={i} />
          ))}
        </div>
      </SortableContext>
    </section>
  );
}
