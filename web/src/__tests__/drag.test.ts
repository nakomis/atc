import { describe, expect, test } from 'vitest';
import { dropToRequest } from '../drag';
import { makeBoard } from './fixtures';

const board = makeBoard();

describe('dropToRequest', () => {
  test('dropping a module card on another column requests a move to the bottom', () => {
    expect(dropToRequest({ kind: 'module', id: 'm2' }, { column: 'next' }, board)).toEqual({
      kind: 'module',
      id: 'm2',
      to_column: 'next',
      before_id: null,
    });
  });

  test('dropping a module row onto a sibling in its card requests a reorder', () => {
    expect(
      dropToRequest(
        { kind: 'module', id: 'm3', projectId: 'p1' },
        { moduleId: 'm1', projectId: 'p1' },
        board,
      ),
    ).toEqual({ project_id: 'p1', module_id: 'm3', before_id: 'm1' });
  });

  test('dropping a card on itself does nothing', () => {
    expect(
      dropToRequest({ kind: 'project', id: 'p1' }, { cardId: 'p1', column: 'backlog' }, board),
    ).toBeNull();
  });

  test('dragging a module row down onto the last sibling sends it to the bottom', () => {
    expect(
      dropToRequest(
        { kind: 'module', id: 'm1', projectId: 'p1' },
        { moduleId: 'm3', projectId: 'p1' },
        board,
      ),
    ).toEqual({ project_id: 'p1', module_id: 'm1', before_id: null });
  });

  test('dragging a module row onto itself does nothing', () => {
    expect(
      dropToRequest(
        { kind: 'module', id: 'm1', projectId: 'p1' },
        { moduleId: 'm1', projectId: 'p1' },
        board,
      ),
    ).toBeNull();
  });

  test('dragging a card down its column lands after the card it is dropped on', () => {
    expect(
      dropToRequest({ kind: 'project', id: 'p1' }, { cardId: 'm2', column: 'backlog' }, board),
    ).toEqual({ kind: 'project', id: 'p1', to_column: 'backlog', before_id: 'p3' });
  });

  test('dragging a card up its column lands before the card it is dropped on', () => {
    expect(
      dropToRequest({ kind: 'project', id: 'p3' }, { cardId: 'p1', column: 'backlog' }, board),
    ).toEqual({ kind: 'project', id: 'p3', to_column: 'backlog', before_id: 'p1' });
  });

  test('dropping a card on a card in another column lands before it', () => {
    expect(
      dropToRequest({ kind: 'module', id: 'm2' }, { cardId: 'p2', column: 'next' }, board),
    ).toEqual({ kind: 'module', id: 'm2', to_column: 'next', before_id: 'p2' });
  });

  test('a module row dragged out of its card onto another column card moves the module', () => {
    expect(
      dropToRequest(
        { kind: 'module', id: 'm1', projectId: 'p1' },
        { cardId: 'm5', column: 'next' },
        board,
      ),
    ).toEqual({ kind: 'module', id: 'm1', to_column: 'next', before_id: 'm5' });
  });

  test("a module row dropped on another project's module lands before that project card", () => {
    expect(
      dropToRequest(
        { kind: 'module', id: 'm1', projectId: 'p1' },
        { moduleId: 'm4', projectId: 'p2' },
        board,
      ),
    ).toEqual({ kind: 'module', id: 'm1', to_column: 'next', before_id: 'p2' });
  });

  test('a module row dropped on its own card or column does nothing', () => {
    const row = { kind: 'module' as const, id: 'm1', projectId: 'p1' };
    expect(dropToRequest(row, { cardId: 'p1', column: 'backlog' }, board)).toBeNull();
    expect(dropToRequest(row, { column: 'backlog' }, board)).toBeNull();
  });

  test('dropping on the empty part of its own column sends a card to the bottom unless it is last', () => {
    expect(dropToRequest({ kind: 'project', id: 'p3' }, { column: 'backlog' }, board)).toBeNull();
    expect(dropToRequest({ kind: 'project', id: 'p1' }, { column: 'backlog' }, board)).toEqual({
      kind: 'project',
      id: 'p1',
      to_column: 'backlog',
      before_id: null,
    });
  });

  test('a drop on something no longer on the board does nothing', () => {
    expect(
      dropToRequest({ kind: 'module', id: 'm2' }, { moduleId: 'gone', projectId: 'px' }, board),
    ).toBeNull();
  });
});
