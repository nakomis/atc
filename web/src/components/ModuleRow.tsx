import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { useState } from 'react';
import { useActions } from '../actions';
import type { DragRef, DropRef } from '../drag';
import type { Card, ModuleView } from '../types';
import { MoveMenu, type MoveOption } from './MoveMenu';
import { Points } from './Points';
import { TicketList } from './TicketList';

interface Props {
  module: ModuleView;
  card: Card;
  column: string;
  index: number;
}

/** One module inside a project card: drag handle, name (expands its tickets), points, Move to…. */
export function ModuleRow({ module, card, column, index }: Props) {
  const actions = useActions();
  const [open, setOpen] = useState(false);
  const ref: DragRef = { kind: 'module', id: module.id, projectId: card.id };
  const drop: DropRef = { moduleId: module.id, projectId: card.id };
  const sortable = useSortable({ id: `row:${module.id}`, data: { ref, drop } });
  const name = `${card.identifier} · ${module.name}`;

  const siblings = card.modules;
  const reorder = (before_id: string | null) =>
    actions.onReorder({ project_id: card.project_id, module_id: module.id, before_id });
  const options: MoveOption[] = [];
  if (index > 0) options.push({ label: 'Up', onSelect: () => reorder(siblings[index - 1].id) });
  if (index < siblings.length - 1) {
    options.push({ label: 'Down', onSelect: () => reorder(siblings[index + 2]?.id ?? null) });
  }
  for (const c of actions.columns) {
    if (c.key !== column) {
      options.push({
        label: c.label,
        onSelect: () =>
          actions.onMove({ kind: 'module', id: module.id, to_column: c.key, before_id: null }),
      });
    }
  }

  return (
    <li
      ref={sortable.setNodeRef}
      style={{
        transform: CSS.Translate.toString(sortable.transform),
        transition: sortable.transition,
      }}
      className={sortable.isDragging ? 'relative z-10 opacity-70' : undefined}
    >
      <div className="flex items-center gap-1">
        <button
          type="button"
          ref={sortable.setActivatorNodeRef}
          aria-label={`Drag ${name}`}
          className="cursor-grab touch-none px-0.5 text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200"
          {...sortable.attributes}
          {...sortable.listeners}
        >
          ⋮⋮
        </button>
        <button
          type="button"
          aria-expanded={open}
          onClick={() => setOpen((o) => !o)}
          className={`min-w-0 truncate text-left hover:underline ${module.unsorted ? 'italic text-neutral-500' : ''}`}
        >
          {module.name}
        </button>
        <Points points={module.points} unestimated={module.unestimated} />
        <MoveMenu label={name} options={options} />
      </div>
      {open && (
        <TicketList
          module={module}
          maxPoints={actions.maxPoints}
          onSaved={actions.onPointsSaved}
          onFailed={actions.onPointsSaved}
        />
      )}
    </li>
  );
}
