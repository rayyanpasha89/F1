import React from 'react';
import { render, screen, fireEvent, waitFor, cleanup, within } from '@testing-library/react';
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

it('sends at most three compact safe conversation turns', async () => {
  const secret = 'access-code-SENTINEL';
  const messages = [1, 2, 3, 4].map((id) => ({
    question: `Question ${id}`,
    race_id: 1100 + id,
    response: {
      intent: 'statistics',
      answer: `private-answer-${id}`,
      sql: `SELECT private_sql_${id}`,
      result: { columns: ['private'], rows: [[id]] },
      provider_calls: [{ raw: `private-provider-${id}` }],
      trace: {
        entities: [
          {
            kind: 'drivers',
            id,
            name: `Driver ${id}`,
            score: 1,
            reasons: ['full_name'],
          },
        ],
      },
    },
  }));
  sessionStorage.setItem('f1-chat', JSON.stringify(messages));
  const fetch = vi.fn().mockImplementation(async (url) => ({
    ok: true,
    json: async () =>
      url.endsWith('/chat/config')
        ? { requires_access_code: true }
        : { intent: 'clarify', answer: 'Specify the comparison.' },
  }));
  vi.stubGlobal('fetch', fetch);
  render(
    <MemoryRouter>
      <StrategistChat />
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByRole('button', { name: 'Ask the strategist' }));
  fireEvent.change(await screen.findByLabelText('Chat access code'), {
    target: { value: secret },
  });
  fireEvent.change(screen.getByLabelText('Your F1 question'), {
    target: { value: 'Compare them now' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Ask question' }));
  await screen.findByText('Specify the comparison.');

  const post = fetch.mock.calls.find((call) => call[1]?.method === 'POST');
  const body = JSON.parse(post[1].body);
  assertSafeConversation(body.conversation);
  expect(body.conversation.map((turn) => turn.question)).toEqual([
    'Question 2',
    'Question 3',
    'Question 4',
  ]);
  expect(body.conversation[0].entities).toEqual([{ kind: 'drivers', id: 2, name: 'Driver 2' }]);
  expect(post[1].headers['x-chat-access-code']).toBe(secret);
  expect(post[1].body).not.toContain(secret);
  expect(post[1].body).not.toContain('private-answer');
  expect(post[1].body).not.toContain('private_sql');
  expect(post[1].body).not.toContain('private-provider');
});

function assertSafeConversation(conversation) {
  expect(conversation).toHaveLength(3);
  for (const turn of conversation) {
    expect(Object.keys(turn).sort()).toEqual(['entities', 'intent', 'question', 'race_id']);
  }
}

it('renders a readable audit trace while legacy responses remain supported', async () => {
  const fetch = vi.fn().mockImplementation(async (url) => ({
    ok: true,
    json: async () =>
      url.endsWith('/chat/config')
        ? { requires_access_code: false }
        : {
            intent: 'statistics',
            status: 'executed',
            answer: 'wins: 105',
            trace: {
              original_question: 'Hamliton wins?',
              interpreted_question: 'hamilton wins?',
              variants: ['Hamliton wins?', 'hamilton wins?'],
              route: 'statistics',
              entities: [
                {
                  kind: 'drivers',
                  id: 1,
                  name: 'Lewis Hamilton',
                  score: 0.95,
                  reasons: ['edit_similarity'],
                },
              ],
              tables: ['drivers', 'results'],
              attempts: [
                {
                  number: 1,
                  outcome: 'rejected',
                  failure_category: 'validation_rejected',
                },
                { number: 2, outcome: 'executed', failure_category: null },
              ],
              provider_call_count: 3,
              provider_elapsed_ms: 3900,
              repair_count: 1,
              total_elapsed_ms: 4012.4,
            },
          },
  }));
  vi.stubGlobal('fetch', fetch);
  render(
    <MemoryRouter>
      <StrategistChat />
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByRole('button', { name: 'Ask the strategist' }));
  fireEvent.change(screen.getByLabelText('Your F1 question'), {
    target: { value: 'Hamliton wins?' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Ask question' }));
  await screen.findByText('wins: 105');

  const disclosure = screen.getByText('How this answer was built').closest('details');
  fireEvent.click(within(disclosure).getByText('How this answer was built'));
  expect(within(disclosure).getByText('hamilton wins?')).toBeInTheDocument();
  expect(within(disclosure).getByText('Statistics')).toBeInTheDocument();
  expect(within(disclosure).getByText('Lewis Hamilton')).toBeInTheDocument();
  expect(within(disclosure).getByText('drivers, results')).toBeInTheDocument();
  expect(within(disclosure).getByText('2 (1 repair)')).toBeInTheDocument();
  expect(within(disclosure).getByText('3')).toBeInTheDocument();
  expect(within(disclosure).getByText('4.01 s')).toBeInTheDocument();
});
