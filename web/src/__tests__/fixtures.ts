import { vi } from 'vitest';
import type { Board, ItemView, ModuleView, ProjectMeta } from '../types';

function item(ref: string, points: number | null, id = ref.toLowerCase()): ItemView {
  return {
    id,
    ref,
    name: `Ticket ${ref}`,
    state: 'Todo',
    state_group: 'unstarted',
    priority: 'none',
    points,
    points_source: points === null ? null : 'claude-estimate',
    url: `https://plane.home.nakomis.com/nakomis/browse/${ref}/`,
  };
}

function mod(id: string, name: string, items: ItemView[], unsorted = false): ModuleView {
  return {
    id,
    name,
    unsorted,
    status: unsorted ? null : 'in-progress',
    points: items.reduce((n, i) => n + (i.points ?? 0), 0),
    unestimated: items.filter((i) => i.points === null).length,
    items,
  };
}

export const moduleWithTwoItems = mod('m1', 'M1', [item('HOME-1', 3), item('HOME-2', null)]);

export function makeBoard(): Board {
  const m3 = mod('m3', 'M3', [item('HOME-3', 5)]);
  const m2 = mod('m2', 'M2', [item('HOME-4', 2)]);
  const m4 = mod('m4', 'Alexa skill', [item('RECIP-1', 15), item('RECIP-2', null)]);
  const u2 = mod('u2', 'Unsorted', [item('RECIP-3', 20)], true);
  const m5 = mod('m5', 'CV chat privacy', [item('NAKIS-1', 6)]);
  return {
    max_points: 100,
    generated_at: '2026-10-18T20:00:00+00:00',
    columns: [
      {
        key: 'backlog',
        label: 'Backlog',
        points: 10,
        unestimated: 1,
        cards: [
          {
            kind: 'project',
            id: 'p1',
            project_id: 'p1',
            identifier: 'HOME',
            label: 'Home infra',
            points: 8,
            unestimated: 1,
            modules: [moduleWithTwoItems, m3],
          },
          {
            kind: 'module',
            id: 'm2',
            project_id: 'p1',
            identifier: 'HOME',
            label: 'HOME · M2',
            points: 2,
            unestimated: 0,
            modules: [m2],
          },
          {
            kind: 'project',
            id: 'p3',
            project_id: 'p3',
            identifier: 'SINT',
            label: 'Sinter',
            points: 0,
            unestimated: 0,
            modules: [],
          },
        ],
      },
      {
        key: 'next',
        label: 'Up next',
        points: 41,
        unestimated: 12,
        cards: [
          {
            kind: 'project',
            id: 'p2',
            project_id: 'p2',
            identifier: 'RECIP',
            label: 'Recipator',
            points: 35,
            unestimated: 1,
            modules: [m4, u2],
          },
          {
            kind: 'module',
            id: 'm5',
            project_id: 'p4',
            identifier: 'NAKIS',
            label: 'NAKIS · CV chat privacy',
            points: 6,
            unestimated: 0,
            modules: [m5],
          },
        ],
      },
      { key: 'in_progress', label: 'In progress', points: 0, unestimated: 0, cards: [] },
    ],
  };
}

export const homeMeta: ProjectMeta = {
  id: 'p1',
  identifier: 'HOME',
  name: 'Home infra',
  column: 'backlog',
  repo: 'nakomis/home-infra',
  deploys: true,
  deploy_action: 'make apply',
  bau_enabled: false,
};

export function respond(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: `HTTP ${status}`,
    json: async () => body,
  };
}

type Handler = (url: string, init: RequestInit) => ReturnType<typeof respond>;

/** A fetch stub routed on "METHOD path"; unknown routes answer 404. */
export function mockApi(routes: Record<string, Handler | unknown>) {
  const fetchMock = vi.fn(async (url: string, init: RequestInit = {}) => {
    const key = `${init.method ?? 'GET'} ${url}`;
    if (!(key in routes)) return respond({ detail: `no route ${key}` }, 404);
    const route = routes[key];
    return typeof route === 'function' ? (route as Handler)(url, init) : respond(route);
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

export function lastBody(fetchMock: ReturnType<typeof mockApi>): string {
  const call = fetchMock.mock.calls.at(-1);
  return String(call?.[1]?.body);
}
