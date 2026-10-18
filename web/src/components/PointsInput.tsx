import { useState } from 'react';
import { setPoints } from '../api';
import type { ItemView } from '../types';

interface Props {
  item: ItemView;
  maxPoints: number;
  onSaved: () => void;
  /** A refused save: the board may have moved on (item deleted, archived), so reload it. */
  onFailed: () => void;
  onError: (message: string | null) => void;
}

/**
 * Inline points editor: saves on Enter or on leaving the field, always as Martin's number.
 * Keyed on the item's points by its parent, so a reloaded board with a new number remounts it.
 */
export function PointsInput({ item, maxPoints, onSaved, onFailed, onError }: Props) {
  const original = item.points === null ? '' : String(item.points);
  const [value, setValue] = useState(original);
  const [saved, setSaved] = useState(original);

  const commit = async () => {
    if (value === saved) return;
    if (value === '') {
      setValue(saved); // points can be changed, not removed
      return;
    }
    const n = Number(value);
    if (!Number.isInteger(n) || n < 1 || n > maxPoints) {
      onError(`Points must be a whole number from 1 to ${maxPoints}.`);
      return;
    }
    onError(null);
    const before = saved;
    setSaved(value); // so a blur straight after Enter does not send it twice
    try {
      await setPoints(item.id, n);
      onSaved();
    } catch (e) {
      setSaved(before);
      setValue(before);
      onError(e instanceof Error ? e.message : String(e));
      onFailed();
    }
  };

  return (
    <input
      type="number"
      inputMode="numeric"
      min={1}
      max={maxPoints}
      step={1}
      aria-label={`Points for ${item.ref}`}
      placeholder="?"
      value={value}
      onChange={(e) => setValue(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          void commit();
        }
      }}
      onBlur={() => void commit()}
      className="w-14 shrink-0 rounded border border-neutral-300 bg-transparent px-1 text-right tabular-nums dark:border-neutral-700"
    />
  );
}
