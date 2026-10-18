import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, test, vi } from 'vitest';
import { TicketList } from '../components/TicketList';
import { lastBody, mockApi, moduleWithTwoItems, respond } from './fixtures';

afterEach(() => vi.unstubAllGlobals());

describe('TicketList', () => {
  test('lists tickets in the order given with their points', () => {
    render(<TicketList module={moduleWithTwoItems} />);
    const links = screen.getAllByRole('link').map((a) => a.textContent);
    expect(links).toEqual(['HOME-1', 'HOME-2']);
    expect(screen.getByLabelText('Points for HOME-1')).toHaveValue(3);
    expect(screen.getByLabelText('Points for HOME-2')).toHaveValue(null);
  });

  test('editing points sends source martin', async () => {
    const fetchMock = mockApi({ 'PUT /api/work-items/home-1/points': { id: 'home-1', points: 4 } });
    const onSaved = vi.fn();
    const user = userEvent.setup();
    render(<TicketList module={moduleWithTwoItems} onSaved={onSaved} />);
    await user.clear(screen.getByLabelText('Points for HOME-1'));
    await user.type(screen.getByLabelText('Points for HOME-1'), '4{Enter}');
    expect(JSON.parse(lastBody(fetchMock))).toEqual({ points: 4, source: 'martin' });
    expect(onSaved).toHaveBeenCalled();
  });

  test('points outside 1..max_points are rejected before sending', async () => {
    const fetchMock = mockApi({});
    const user = userEvent.setup();
    render(<TicketList module={moduleWithTwoItems} maxPoints={100} />);
    const input = screen.getByLabelText('Points for HOME-1');
    await user.clear(input);
    await user.type(input, '0{Enter}');
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Points must be a whole number from 1 to 100.',
    );
    await user.clear(input);
    await user.type(input, '101{Enter}');
    expect(screen.getByRole('alert')).toHaveTextContent('from 1 to 100');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test('an unchanged value is not sent, and leaving the field saves it', async () => {
    const fetchMock = mockApi({ 'PUT /api/work-items/home-2/points': { id: 'home-2', points: 7 } });
    const user = userEvent.setup();
    render(<TicketList module={moduleWithTwoItems} />);
    await user.click(screen.getByLabelText('Points for HOME-1'));
    await user.keyboard('{Enter}');
    expect(fetchMock).not.toHaveBeenCalled();
    await user.type(screen.getByLabelText('Points for HOME-2'), '7');
    await user.tab();
    expect(JSON.parse(lastBody(fetchMock))).toEqual({ points: 7, source: 'martin' });
  });

  test('a refused save shows the API message', async () => {
    mockApi({
      'PUT /api/work-items/home-1/points': () => respond({ detail: 'no work item home-1' }, 404),
    });
    const user = userEvent.setup();
    render(<TicketList module={moduleWithTwoItems} />);
    await user.clear(screen.getByLabelText('Points for HOME-1'));
    await user.type(screen.getByLabelText('Points for HOME-1'), '9{Enter}');
    expect(await screen.findByRole('alert')).toHaveTextContent('no work item home-1');
  });

  test('an empty module says so', () => {
    render(<TicketList module={{ ...moduleWithTwoItems, items: [] }} />);
    expect(screen.getByText('No open tickets.')).toBeInTheDocument();
  });
});
