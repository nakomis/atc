import { SortableContext, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { useState } from 'react';
import { useActions } from '../actions';
import type { DragRef, DropRef } from '../drag';
import type { Card as CardData, Column } from '../types';
import { ModuleRow } from './ModuleRow';
import { MoveMenu, type MoveOption } from './MoveMenu';
import { Points } from './Points';
import { TicketList } from './TicketList';

interface Props {
  card: CardData;
  column: Column;
  index: number;
}

/** A whole project (📁, modules nested and sortable) or a single module (▫️ "IDENT · Module"). */
export function Card({ card, column, index }: Props) {
  const actions = useActions();
  const [open, setOpen] = useState(false);
  const ref: DragRef = { kind: card.kind, id: card.id };
  const drop: DropRef = { cardId: card.id, column: column.key };
  const sortable = useSortable({ id: `card:${card.id}`, data: { ref, drop } });
  const isProject = card.kind === 'project';
  const name = isProject ? `${card.identifier} ${card.label}` : card.label;
  const empty = card.modules.every((m) => m.items.length === 0);

  const move = (to_column: string, before_id: string | null) =>
    actions.onMove({ kind: card.kind, id: card.id, to_column, before_id });
  const cards = column.cards;
  const options: MoveOption[] = [];
  if (index > 0)
    options.push({ label: 'Up', onSelect: () => move(column.key, cards[index - 1].id) });
  if (index < cards.length - 1) {
    options.push({ label: 'Down', onSelect: () => move(column.key, cards[index + 2]?.id ?? null) });
  }
  for (const c of actions.columns) {
    if (c.key !== column.key) options.push({ label: c.label, onSelect: () => move(c.key, null) });
  }

  // The module card's label is "IDENT · Module name"; the identifier part is shown muted.
  const prefix = `${card.identifier} · `;
  const moduleName = card.label.startsWith(prefix) ? card.label.slice(prefix.length) : card.label;

  return (
    <article
      ref={sortable.setNodeRef}
      aria-label={name}
      style={{
        transform: CSS.Translate.toString(sortable.transform),
        transition: sortable.transition,
      }}
      className={[
        'rounded-md border bg-white p-2 text-sm dark:bg-neutral-900',
        isProject
          ? 'border-neutral-300 dark:border-neutral-700'
          : 'border-dashed border-neutral-400 dark:border-neutral-600',
        empty ? 'opacity-50' : '',
        sortable.isDragging ? 'relative z-10 shadow-lg' : '',
      ].join(' ')}
    >
      <div className="flex items-center gap-1">
        <button
          type="button"
          ref={sortable.setActivatorNodeRef}
          aria-label={`Drag ${isProject ? card.identifier : card.label}`}
          className="cursor-grab touch-none px-0.5 text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200"
          {...sortable.attributes}
          {...sortable.listeners}
        >
          ⋮⋮
        </button>
        {isProject ? (
          <span className="min-w-0 truncate">
            <span aria-hidden="true">📁 </span>
            <b>{card.identifier}</b> {card.label}
          </span>
        ) : (
          <button
            type="button"
            aria-expanded={open}
            onClick={() => setOpen((o) => !o)}
            className="min-w-0 truncate text-left hover:underline"
          >
            <span aria-hidden="true">▫️ </span>
            <span className="text-neutral-500">{card.identifier} ·</span> {moduleName}
          </button>
        )}
        <Points points={card.points} unestimated={card.unestimated} />
        {isProject && (
          <button
            type="button"
            aria-label={`Settings for ${card.identifier}`}
            title="Project settings"
            onClick={() => actions.onSettings(card.project_id)}
            className="rounded px-1 text-neutral-500 hover:bg-neutral-200 hover:text-neutral-900 dark:hover:bg-neutral-700 dark:hover:text-neutral-100"
          >
            ⚙
          </button>
        )}
        <MoveMenu label={isProject ? card.identifier : card.label} options={options} />
      </div>
      {isProject && card.modules.length === 0 && (
        <p className="mt-1 pl-5 text-xs text-neutral-500">nothing here</p>
      )}
      {isProject && card.modules.length > 0 && (
        <SortableContext
          items={card.modules.map((m) => `row:${m.id}`)}
          strategy={verticalListSortingStrategy}
        >
          <ul className="mt-1 space-y-0.5 pl-3 text-neutral-700 dark:text-neutral-300">
            {card.modules.map((m, i) => (
              <ModuleRow key={m.id} module={m} card={card} column={column.key} index={i} />
            ))}
          </ul>
        </SortableContext>
      )}
      {!isProject && open && card.modules[0] && (
        <TicketList
          module={card.modules[0]}
          maxPoints={actions.maxPoints}
          onSaved={actions.onPointsSaved}
        />
      )}
    </article>
  );
}
