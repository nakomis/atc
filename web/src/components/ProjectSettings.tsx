import { useEffect, useId, useState } from 'react';
import { getProject, putProject } from '../api';
import type { ProjectMeta, ProjectPatch } from '../types';

interface Props {
  projectId: string;
  onClose: () => void;
}

const messageOf = (e: unknown) => (e instanceof Error ? e.message : String(e));

/** Repo, deploys, deploy action and BAU enabled for one project. Saves only what changed. */
export function ProjectSettings({ projectId, onClose }: Props) {
  const [meta, setMeta] = useState<ProjectMeta | null>(null);
  const [repo, setRepo] = useState('');
  const [deploys, setDeploys] = useState(false);
  const [deployAction, setDeployAction] = useState('');
  const [bauEnabled, setBauEnabled] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const titleId = useId();
  const ids = { repo: useId(), deploys: useId(), action: useId(), bau: useId() };

  useEffect(() => {
    let live = true;
    getProject(projectId).then(
      (m) => {
        if (!live) return;
        setMeta(m);
        setRepo(m.repo ?? '');
        setDeploys(m.deploys);
        setDeployAction(m.deploy_action);
        setBauEnabled(m.bau_enabled);
      },
      (e) => live && setError(messageOf(e)),
    );
    return () => {
      live = false;
    };
  }, [projectId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    if (meta === null) return;
    const patch: ProjectPatch = {};
    const newRepo = repo.trim() === '' ? null : repo.trim();
    if (newRepo !== meta.repo) patch.repo = newRepo;
    if (deploys !== meta.deploys) patch.deploys = deploys;
    if (deployAction !== meta.deploy_action) patch.deploy_action = deployAction;
    if (bauEnabled !== meta.bau_enabled) patch.bau_enabled = bauEnabled;
    if (Object.keys(patch).length === 0) {
      onClose();
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await putProject(projectId, patch);
      onClose();
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setSaving(false);
    }
  };

  const field =
    'w-full rounded border border-neutral-300 bg-transparent px-2 py-1 dark:border-neutral-700';
  return (
    <div className="fixed inset-0 z-30 flex items-start justify-center bg-black/30 p-4 pt-16">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="w-full max-w-md rounded-lg bg-white p-4 shadow-xl dark:bg-neutral-900"
      >
        <div className="mb-3 flex items-center">
          <h2 id={titleId} className="font-semibold">
            {meta ? `${meta.identifier} settings` : 'Project settings'}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="ml-auto rounded px-2 text-neutral-500 hover:bg-neutral-200 dark:hover:bg-neutral-700"
          >
            Close
          </button>
        </div>
        {error && (
          <p role="alert" className="mb-2 text-sm text-red-600 dark:text-red-400">
            {error}
          </p>
        )}
        {meta === null ? (
          !error && <p className="text-sm text-neutral-500">Loading…</p>
        ) : (
          <form onSubmit={save} className="space-y-3 text-sm">
            <div>
              <label htmlFor={ids.repo} className="mb-1 block font-medium">
                Repo
              </label>
              <input
                id={ids.repo}
                className={field}
                placeholder="owner/name"
                value={repo}
                onChange={(e) => setRepo(e.target.value)}
              />
            </div>
            <div className="flex items-center gap-2">
              <input
                id={ids.deploys}
                type="checkbox"
                checked={deploys}
                onChange={(e) => setDeploys(e.target.checked)}
              />
              <label htmlFor={ids.deploys}>Deploys</label>
            </div>
            <div>
              <label htmlFor={ids.action} className="mb-1 block font-medium">
                Deploy action
              </label>
              <input
                id={ids.action}
                className={field}
                value={deployAction}
                onChange={(e) => setDeployAction(e.target.value)}
              />
            </div>
            <div className="flex items-center gap-2">
              <input
                id={ids.bau}
                type="checkbox"
                checked={bauEnabled}
                onChange={(e) => setBauEnabled(e.target.checked)}
              />
              <label htmlFor={ids.bau}>BAU enabled</label>
            </div>
            <div className="flex justify-end">
              <button
                type="submit"
                disabled={saving}
                className="rounded bg-sky-700 px-3 py-1 font-medium text-white hover:bg-sky-800 disabled:opacity-50"
              >
                Save
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
