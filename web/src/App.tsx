import { useCallback, useEffect, useMemo, useState } from 'react';
import { ActionsContext, type BoardActions } from './actions';
import { getBoard, move, reorder } from './api';
import { Board } from './components/Board';
import { ProjectSettings } from './components/ProjectSettings';
import type { Board as BoardData } from './types';

const messageOf = (e: unknown) => (e instanceof Error ? e.message : String(e));

export default function App() {
  const [board, setBoard] = useState<BoardData | null>(null);
  const [showClosed, setShowClosed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [settingsFor, setSettingsFor] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setBoard(await getBoard(showClosed));
    } catch (e) {
      setError(messageOf(e));
    }
  }, [showClosed]);

  useEffect(() => {
    void load();
  }, [load]);

  // Every write answers with the whole board; a refused one shows why and reloads the truth.
  const write = useCallback(
    async (send: () => Promise<BoardData>) => {
      try {
        setBoard(await send());
        setError(null);
      } catch (e) {
        setError(messageOf(e));
        await load();
      }
    },
    [load],
  );

  const actions = useMemo<BoardActions>(
    () => ({
      columns: board?.columns.map((c) => ({ key: c.key, label: c.label })) ?? [],
      maxPoints: board?.max_points ?? 100,
      onMove: (req) => void write(() => move(req, showClosed)),
      onReorder: (req) => void write(() => reorder(req, showClosed)),
      onPointsSaved: () => void load(),
      onSettings: setSettingsFor,
    }),
    [board, write, load, showClosed],
  );

  const closeSettings = useCallback(() => setSettingsFor(null), []);

  return (
    <div className="mx-auto max-w-7xl p-4">
      <header className="mb-4 flex flex-wrap items-center gap-4">
        <h1 className="text-xl font-bold">ATC</h1>
        <label className="ml-auto flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={showClosed}
            onChange={(e) => setShowClosed(e.target.checked)}
          />
          Show closed
        </label>
      </header>
      {error && (
        <div
          role="alert"
          className="mb-4 flex items-center gap-2 rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-200"
        >
          <span>{error}</span>
          <button type="button" onClick={() => setError(null)} className="ml-auto underline">
            Dismiss
          </button>
        </div>
      )}
      {board === null ? (
        !error && <p className="text-neutral-500">Loading the board…</p>
      ) : (
        <ActionsContext.Provider value={actions}>
          <Board board={board} />
        </ActionsContext.Provider>
      )}
      {settingsFor !== null && <ProjectSettings projectId={settingsFor} onClose={closeSettings} />}
    </div>
  );
}
