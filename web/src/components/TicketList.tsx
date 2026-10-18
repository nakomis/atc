import { useState } from 'react';
import type { ModuleView } from '../types';
import { PointsInput } from './PointsInput';

interface Props {
  module: ModuleView;
  maxPoints?: number;
  onSaved?: () => void;
}

/** A module's open tickets in Plane order, each linking to Plane, with inline points. */
export function TicketList({ module, maxPoints = 100, onSaved = () => {} }: Props) {
  const [error, setError] = useState<string | null>(null);
  if (module.items.length === 0) {
    return <p className="py-1 pl-6 text-xs text-neutral-500">No open tickets.</p>;
  }
  return (
    <div className="pb-1 pl-6">
      {error && (
        <p role="alert" className="text-xs text-red-600 dark:text-red-400">
          {error}
        </p>
      )}
      <ul className="space-y-0.5 text-xs">
        {module.items.map((item) => (
          <li key={item.id} className="flex items-center gap-2">
            <a
              href={item.url}
              target="_blank"
              rel="noopener noreferrer"
              className="shrink-0 font-mono text-sky-700 hover:underline dark:text-sky-400"
            >
              {item.ref}
            </a>
            <span className="min-w-0 flex-1 truncate" title={item.name}>
              {item.name}
            </span>
            <PointsInput item={item} maxPoints={maxPoints} onSaved={onSaved} onError={setError} />
          </li>
        ))}
      </ul>
    </div>
  );
}
