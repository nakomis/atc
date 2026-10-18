import type { Board, MoveRequest, ProjectMeta, ProjectPatch, ReorderRequest } from './types';

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

/** FastAPI answers `{detail: str}`, or `{detail: [{msg}]}` for a validation error. */
function detailOf(body: unknown): string | null {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) => (d as { msg?: unknown })?.msg)
      .filter((m) => typeof m === 'string');
    if (msgs.length) return msgs.join('; ');
  }
  return null;
}

async function call<T>(method: string, url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let parsed: unknown = null;
  try {
    parsed = await res.json();
  } catch {
    parsed = null;
  }
  if (!res.ok) {
    throw new ApiError(res.status, detailOf(parsed) ?? `${res.status} ${res.statusText}`.trim());
  }
  return parsed as T;
}

const withAll = (path: string, all?: boolean) => (all ? `${path}?all=true` : path);

export function getBoard(all?: boolean): Promise<Board> {
  return call('GET', withAll('/api/board', all));
}

/** `all` keeps the returned board in "show closed" mode. */
export function move(req: MoveRequest, all?: boolean): Promise<Board> {
  return call('POST', withAll('/api/move', all), req);
}

export function reorder(req: ReorderRequest, all?: boolean): Promise<Board> {
  return call('POST', withAll('/api/reorder', all), req);
}

export async function setPoints(id: string, points: number): Promise<void> {
  await call('PUT', `/api/work-items/${encodeURIComponent(id)}/points`, {
    points,
    source: 'martin',
  });
}

export function getProject(id: string): Promise<ProjectMeta> {
  return call('GET', `/api/projects/${encodeURIComponent(id)}`);
}

export function putProject(id: string, patch: ProjectPatch): Promise<ProjectMeta> {
  return call('PUT', `/api/projects/${encodeURIComponent(id)}`, patch);
}
