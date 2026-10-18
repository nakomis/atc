import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, test, vi } from 'vitest';
import { ProjectSettings } from '../components/ProjectSettings';
import { homeMeta, mockApi, respond } from './fixtures';

afterEach(() => vi.unstubAllGlobals());

describe('ProjectSettings', () => {
  test('settings panel saves bau_enabled', async () => {
    const fetchMock = mockApi({
      'GET /api/projects/p1': homeMeta,
      'PUT /api/projects/p1': { ...homeMeta, bau_enabled: true },
    });
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<ProjectSettings projectId="p1" onClose={onClose} />);
    await user.click(await screen.findByRole('checkbox', { name: 'BAU enabled' }));
    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/projects/p1',
      expect.objectContaining({ method: 'PUT', body: JSON.stringify({ bau_enabled: true }) }),
    );
    expect(onClose).toHaveBeenCalled();
  });

  test('shows the current metadata and sends only what changed; a blank repo clears it', async () => {
    const fetchMock = mockApi({
      'GET /api/projects/p1': homeMeta,
      'PUT /api/projects/p1': homeMeta,
    });
    const user = userEvent.setup();
    render(<ProjectSettings projectId="p1" onClose={() => {}} />);
    const repo = await screen.findByLabelText('Repo');
    expect(repo).toHaveValue('nakomis/home-infra');
    expect(screen.getByRole('checkbox', { name: 'Deploys' })).toBeChecked();
    await user.clear(repo);
    await user.clear(screen.getByLabelText('Deploy action'));
    await user.type(screen.getByLabelText('Deploy action'), 'make deploy');
    await user.click(screen.getByRole('checkbox', { name: 'Deploys' }));
    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(JSON.parse(String(fetchMock.mock.calls.at(-1)?.[1]?.body))).toEqual({
      repo: null,
      deploy_action: 'make deploy',
      deploys: false,
    });
  });

  test('saving with nothing changed just closes', async () => {
    const fetchMock = mockApi({ 'GET /api/projects/p1': homeMeta });
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<ProjectSettings projectId="p1" onClose={onClose} />);
    await user.click(await screen.findByRole('button', { name: 'Save' }));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalled();
  });

  test('a refused save keeps the panel open with the message', async () => {
    mockApi({
      'GET /api/projects/p1': homeMeta,
      'PUT /api/projects/p1': () =>
        respond({ detail: [{ msg: 'Value error, repo must look like owner/name' }] }, 422),
    });
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<ProjectSettings projectId="p1" onClose={onClose} />);
    const repo = await screen.findByLabelText('Repo');
    await user.clear(repo);
    await user.type(repo, 'not a repo');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('repo must look like owner/name');
    expect(onClose).not.toHaveBeenCalled();
  });

  test('a project that cannot be loaded says so', async () => {
    mockApi({ 'GET /api/projects/p1': () => respond({ detail: 'no project p1' }, 404) });
    render(<ProjectSettings projectId="p1" onClose={() => {}} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('no project p1');
  });
});
