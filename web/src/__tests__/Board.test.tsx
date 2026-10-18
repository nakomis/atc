import type { DragEndEvent } from '@dnd-kit/core';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, test, vi } from 'vitest';
import App from '../App';
import { collide, dragEndHandler } from '../components/Board';
import { homeMeta, makeBoard, mockApi, respond } from './fixtures';

afterEach(() => vi.unstubAllGlobals());

function boardCalls(fetchMock: ReturnType<typeof mockApi>) {
  return fetchMock.mock.calls.filter((c) => String(c[0]).startsWith('/api/board')).map((c) => c[0]);
}

describe('board', () => {
  test('column headers show points and unestimated counts', async () => {
    mockApi({ 'GET /api/board': makeBoard() });
    render(<App />);
    expect(await screen.findByText('Up next · 41 pts')).toBeInTheDocument();
    expect(screen.getByText('+12 unestimated')).toBeInTheDocument();
    expect(screen.getByText('In progress · 0 pts')).toBeInTheDocument();
  });

  test('columns render left to right in the order the API gives', async () => {
    mockApi({ 'GET /api/board': makeBoard() });
    render(<App />);
    await screen.findByText('Up next · 41 pts');
    const headings = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent);
    expect(headings.map((h) => h?.split(' · ')[0])).toEqual(['Backlog', 'Up next', 'In progress']);
  });

  test('project cards list their modules; module cards carry the project identifier', async () => {
    mockApi({ 'GET /api/board': makeBoard() });
    render(<App />);
    const recip = await screen.findByRole('article', { name: 'RECIP Recipator' });
    expect(within(recip).getByText('Alexa skill')).toBeInTheDocument();
    expect(within(recip).getByText('Unsorted')).toBeInTheDocument();
    expect(screen.getByRole('article', { name: 'HOME · M2' })).toBeInTheDocument();
  });

  test('an empty project card is greyed with "nothing here"', async () => {
    mockApi({ 'GET /api/board': makeBoard() });
    render(<App />);
    const sint = await screen.findByRole('article', { name: 'SINT Sinter' });
    expect(within(sint).getByText('nothing here')).toBeInTheDocument();
    expect(sint.className).toContain('opacity-50');
  });

  test('Move to… posts a move and re-renders from the response', async () => {
    const moved = makeBoard();
    const [card] = moved.columns[0].cards.splice(1, 1);
    moved.columns[2].cards.push(card);
    moved.columns[2].points = 2;
    const fetchMock = mockApi({ 'GET /api/board': makeBoard(), 'POST /api/move': moved });
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole('button', { name: 'Move HOME · M2' }));
    expect(screen.queryByRole('menuitem', { name: 'Backlog' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('menuitem', { name: 'In progress' }));
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/move',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(JSON.parse(String(fetchMock.mock.calls.at(-1)?.[1]?.body))).toEqual({
      kind: 'module',
      id: 'm2',
      to_column: 'in_progress',
      before_id: null,
    });
    expect(await screen.findByText('In progress · 2 pts')).toBeInTheDocument();
  });

  test('Move to… on a card offers up and down within its column', async () => {
    const fetchMock = mockApi({ 'GET /api/board': makeBoard(), 'POST /api/move': makeBoard() });
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole('button', { name: 'Move HOME · M2' }));
    await user.click(screen.getByRole('menuitem', { name: 'Up' }));
    expect(JSON.parse(String(fetchMock.mock.calls.at(-1)?.[1]?.body))).toEqual({
      kind: 'module',
      id: 'm2',
      to_column: 'backlog',
      before_id: 'p1',
    });
    await user.click(screen.getByRole('button', { name: 'Move HOME · M2' }));
    await user.click(screen.getByRole('menuitem', { name: 'Down' }));
    expect(JSON.parse(String(fetchMock.mock.calls.at(-1)?.[1]?.body))).toMatchObject({
      before_id: null,
    });
  });

  test('Move to… on a module row reorders within the card or moves the module out', async () => {
    const fetchMock = mockApi({
      'GET /api/board': makeBoard(),
      'POST /api/reorder': makeBoard(),
      'POST /api/move': makeBoard(),
    });
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole('button', { name: 'Move HOME · M3' }));
    expect(screen.queryByRole('menuitem', { name: 'Down' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('menuitem', { name: 'Up' }));
    expect(fetchMock).toHaveBeenLastCalledWith('/api/reorder', expect.anything());
    expect(JSON.parse(String(fetchMock.mock.calls.at(-1)?.[1]?.body))).toEqual({
      project_id: 'p1',
      module_id: 'm3',
      before_id: 'm1',
    });
    await user.click(screen.getByRole('button', { name: 'Move HOME · M3' }));
    await user.click(screen.getByRole('menuitem', { name: 'Up next' }));
    expect(JSON.parse(String(fetchMock.mock.calls.at(-1)?.[1]?.body))).toEqual({
      kind: 'module',
      id: 'm3',
      to_column: 'next',
      before_id: null,
    });
  });

  test('the Move to… menu closes on Escape', async () => {
    mockApi({ 'GET /api/board': makeBoard() });
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole('button', { name: 'Move HOME · M2' }));
    expect(screen.getByRole('menu')).toBeInTheDocument();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });

  test('a failed move shows the error and reloads the board', async () => {
    const fetchMock = mockApi({
      'GET /api/board': makeBoard(),
      'POST /api/move': () => respond({ detail: 'no module m2' }, 404),
    });
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole('button', { name: 'Move HOME · M2' }));
    await user.click(screen.getByRole('menuitem', { name: 'In progress' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('no module m2');
    await waitFor(() => expect(boardCalls(fetchMock)).toEqual(['/api/board', '/api/board']));
    await user.click(screen.getByRole('button', { name: 'Dismiss' }));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  test('a board that fails to load says so', async () => {
    mockApi({ 'GET /api/board': () => respond({ detail: 'database unreachable' }, 500) });
    render(<App />);
    expect(await screen.findByRole('alert')).toHaveTextContent('database unreachable');
  });

  test('Show closed asks for the whole board and moves keep asking for it', async () => {
    const fetchMock = mockApi({
      'GET /api/board': makeBoard(),
      'GET /api/board?all=true': makeBoard(),
      'POST /api/move?all=true': makeBoard(),
    });
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole('checkbox', { name: 'Show closed' }));
    await waitFor(() => expect(boardCalls(fetchMock)).toContain('/api/board?all=true'));
    await user.click(screen.getByRole('button', { name: 'Move HOME · M2' }));
    await user.click(screen.getByRole('menuitem', { name: 'Up next' }));
    expect(fetchMock).toHaveBeenLastCalledWith('/api/move?all=true', expect.anything());
  });

  test('clicking a module row expands its tickets, linked to Plane in a new tab', async () => {
    mockApi({ 'GET /api/board': makeBoard() });
    const user = userEvent.setup();
    render(<App />);
    const toggle = await screen.findByRole('button', { name: 'M1' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await user.click(toggle);
    const link = screen.getByRole('link', { name: 'HOME-1' });
    expect(link).toHaveAttribute('href', 'https://plane.home.nakomis.com/nakomis/browse/HOME-1/');
    expect(link).toHaveAttribute('target', '_blank');
    expect(screen.getByText('Ticket HOME-1')).toBeInTheDocument();
    await user.click(toggle);
    expect(screen.queryByRole('link', { name: 'HOME-1' })).not.toBeInTheDocument();
  });

  test('a module card expands its tickets too', async () => {
    mockApi({ 'GET /api/board': makeBoard() });
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole('button', { name: 'HOME · M2' }));
    expect(screen.getByRole('link', { name: 'HOME-4' })).toBeInTheDocument();
  });

  test('saving points reloads the board so the totals follow', async () => {
    const fetchMock = mockApi({
      'GET /api/board': makeBoard(),
      'PUT /api/work-items/home-2/points': { id: 'home-2', points: 2 },
    });
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole('button', { name: 'M1' }));
    await user.type(screen.getByLabelText('Points for HOME-2'), '2{Enter}');
    await waitFor(() => expect(boardCalls(fetchMock)).toHaveLength(2));
  });

  test('a refused points save shows the message and reloads the board', async () => {
    const fetchMock = mockApi({
      'GET /api/board': makeBoard(),
      'PUT /api/work-items/home-1/points': () => respond({ detail: 'no work item home-1' }, 404),
    });
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole('button', { name: 'M1' }));
    const input = screen.getByLabelText('Points for HOME-1');
    await user.clear(input);
    await user.type(input, '9{Enter}');
    expect(await screen.findByRole('alert')).toHaveTextContent('no work item home-1');
    await waitFor(() => expect(boardCalls(fetchMock)).toEqual(['/api/board', '/api/board']));
    expect(screen.getByLabelText('Points for HOME-1')).toHaveValue(3);
  });

  test('the gear on a project card opens its settings', async () => {
    mockApi({ 'GET /api/board': makeBoard(), 'GET /api/projects/p1': homeMeta });
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole('button', { name: 'Settings for HOME' }));
    const dialog = await screen.findByRole('dialog', { name: 'HOME settings' });
    expect(await within(dialog).findByDisplayValue('nakomis/home-infra')).toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: 'Close' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});

describe('drag wiring', () => {
  const actions = () => ({
    columns: [],
    maxPoints: 100,
    onMove: vi.fn(),
    onReorder: vi.fn(),
    onPointsSaved: vi.fn(),
    onSettings: vi.fn(),
  });
  const dragEnd = (ref: unknown, drop: unknown) =>
    ({
      active: { id: 'a', data: { current: { ref } } },
      over: drop === undefined ? null : { id: 'o', data: { current: { drop } } },
    }) as unknown as DragEndEvent;

  test('a drop on another column becomes a move; a sibling drop becomes a reorder', () => {
    const a = actions();
    const end = dragEndHandler(makeBoard(), a);
    end(dragEnd({ kind: 'module', id: 'm2' }, { column: 'next' }));
    expect(a.onMove).toHaveBeenCalledWith({
      kind: 'module',
      id: 'm2',
      to_column: 'next',
      before_id: null,
    });
    end(
      dragEnd({ kind: 'module', id: 'm3', projectId: 'p1' }, { moduleId: 'm1', projectId: 'p1' }),
    );
    expect(a.onReorder).toHaveBeenCalledWith({
      project_id: 'p1',
      module_id: 'm3',
      before_id: 'm1',
    });
  });

  test('a drop on nothing, or on itself, sends nothing', () => {
    const a = actions();
    const end = dragEndHandler(makeBoard(), a);
    end(dragEnd({ kind: 'project', id: 'p1' }, undefined));
    end(dragEnd({ kind: 'project', id: 'p1' }, { cardId: 'p1', column: 'backlog' }));
    expect(a.onMove).not.toHaveBeenCalled();
    expect(a.onReorder).not.toHaveBeenCalled();
  });

  test('the innermost target under the pointer wins, and cards ignore module rows', () => {
    const rect = (top: number, height: number) => ({
      top,
      left: 0,
      width: 100,
      height,
      bottom: top + height,
      right: 100,
    });
    const rects = new Map([
      ['col:backlog', rect(0, 500)],
      ['card:p1', rect(10, 100)],
      ['row:m1', rect(40, 20)],
    ]);
    const containers = [...rects.keys()].map((id) => ({ id, data: { current: {} } }));
    const args = (ref: unknown) =>
      ({
        active: { id: 'x', data: { current: { ref } } },
        collisionRect: rect(45, 10),
        droppableRects: rects,
        droppableContainers: containers,
        pointerCoordinates: { x: 50, y: 50 },
      }) as unknown as Parameters<typeof collide>[0];
    expect(collide(args({ kind: 'module', id: 'm3', projectId: 'p1' }))[0].id).toBe('row:m1');
    expect(collide(args({ kind: 'project', id: 'p3' }))[0].id).toBe('card:p1');
    const keyboard = { ...args({ kind: 'project', id: 'p3' }), pointerCoordinates: null };
    expect(collide(keyboard).map((c) => c.id)).not.toContain('row:m1');
  });
});
