import React from 'react';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { it, expect, vi, afterEach } from 'vitest';
import StrategistChat from './StrategistChat';
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  sessionStorage.clear();
});
it('sends the selected race, renders executed SQL, and persists the conversation', async () => {
  const fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      intent: 'statistics',
      status: 'executed',
      answer: 'count: 2',
      sql: 'SELECT COUNT(*) FROM races',
      result: { columns: ['count'], rows: [[2]] },
    }),
  });
  vi.stubGlobal('fetch', fetch);
  render(
    <MemoryRouter initialEntries={['/races/1128']}>
      <StrategistChat />
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByRole('button', { name: 'Ask the strategist' }));
  fireEvent.change(screen.getByLabelText('Your F1 question'), {
    target: { value: 'How many races?' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Ask question' }));
  await screen.findByText('count: 2');
  expect(
    JSON.parse(fetch.mock.calls.find((call) => call[1]?.method === 'POST')[1].body).race_id,
  ).toBe(1128);
  expect(screen.getByText('SELECT COUNT(*) FROM races')).toBeInTheDocument();
  await waitFor(() => expect(JSON.parse(sessionStorage.getItem('f1-chat'))).toHaveLength(1));
  fireEvent.click(screen.getByRole('button', { name: 'Clear' }));
  expect(screen.queryByText('count: 2')).not.toBeInTheDocument();
});
it('keeps a failed question available for retry', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({ detail: 'Bedrock unavailable' }),
    }),
  );
  render(
    <MemoryRouter>
      <StrategistChat />
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByRole('button', { name: 'Ask the strategist' }));
  fireEvent.change(screen.getByLabelText('Your F1 question'), {
    target: { value: 'How many races?' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Ask question' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Bedrock unavailable');
  expect(screen.getByLabelText('Your F1 question')).toHaveValue('How many races?');
});
