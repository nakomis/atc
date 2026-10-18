import { afterEach, describe, expect, test, vi } from 'vitest';
import { ApiError, getBoard, getProject, move, putProject, reorder, setPoints } from '../api';
import { homeMeta, lastBody, makeBoard, mockApi, respond } from './fixtures';

afterEach(() => vi.unstubAllGlobals());

describe('api', () => {
  test('getBoard reads the open board, or everything with all', async () => {
    const fetchMock = mockApi({
      'GET /api/board': makeBoard(),
      'GET /api/board?all=true': makeBoard(),
    });
    expect((await getBoard()).columns).toHaveLength(3);
    await getBoard(true);
    expect(fetchMock.mock.calls.map((c) => c[0])).toEqual(['/api/board', '/api/board?all=true']);
    expect(fetchMock.mock.calls[0][1]?.headers).toEqual({ 'Content-Type': 'application/json' });
  });

  test('move and reorder post JSON and return the new board', async () => {
    const fetchMock = mockApi({
      'POST /api/move': makeBoard(),
      'POST /api/reorder?all=true': makeBoard(),
    });
    const board = await move({ kind: 'module', id: 'm2', to_column: 'next', before_id: null });
    expect(board.columns[1].label).toBe('Up next');
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({
      kind: 'module',
      id: 'm2',
      to_column: 'next',
      before_id: null,
    });
    await reorder({ project_id: 'p1', module_id: 'm3', before_id: 'm1' }, true);
    expect(JSON.parse(lastBody(fetchMock))).toEqual({
      project_id: 'p1',
      module_id: 'm3',
      before_id: 'm1',
    });
  });

  test('setPoints always sends source martin', async () => {
    const fetchMock = mockApi({ 'PUT /api/work-items/i1/points': { id: 'i1', points: 4 } });
    await setPoints('i1', 4);
    expect(JSON.parse(lastBody(fetchMock))).toEqual({ points: 4, source: 'martin' });
  });

  test('project metadata is read and patched', async () => {
    const fetchMock = mockApi({
      'GET /api/projects/p1': homeMeta,
      'PUT /api/projects/p1': { ...homeMeta, bau_enabled: true },
    });
    expect((await getProject('p1')).repo).toBe('nakomis/home-infra');
    expect((await putProject('p1', { bau_enabled: true })).bau_enabled).toBe(true);
    expect(lastBody(fetchMock)).toBe('{"bau_enabled":true}');
  });

  test('a non-2xx answer throws ApiError with the API detail', async () => {
    mockApi({ 'POST /api/move': () => respond({ detail: 'x is not another card' }, 422) });
    const err = await move({ kind: 'project', id: 'p1', to_column: 'x', before_id: null }).catch(
      (e) => e,
    );
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(422);
    expect(err.message).toBe('x is not another card');
  });

  test('validation errors are flattened and unreadable bodies fall back to the status', async () => {
    mockApi({
      'PUT /api/projects/p1': () =>
        respond({ detail: [{ msg: 'repo must look like owner/name' }, { msg: 'bad' }] }, 422),
      'GET /api/projects/p1': () => ({
        ok: false,
        status: 502,
        statusText: 'Bad Gateway',
        json: async () => {
          throw new Error('not json');
        },
      }),
    });
    await expect(putProject('p1', { repo: 'nope' })).rejects.toThrow(
      'repo must look like owner/name; bad',
    );
    await expect(getProject('p1')).rejects.toThrow('502 Bad Gateway');
  });
});
