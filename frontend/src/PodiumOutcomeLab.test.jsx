import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import PodiumOutcomeLab from './PodiumOutcomeLab';

const grid = {
  data: [
    { driver_id: 844, driver_name: 'Charles Leclerc', grid: 1 },
    { driver_id: 857, driver_name: 'Oscar Piastri', grid: 2 },
    { driver_id: 832, driver_name: 'Carlos Sainz', grid: 3 },
    { driver_id: 830, driver_name: 'Max Verstappen', grid: 4 },
  ],
};

const outcomeMap = {
  schema_version: 'f1-podium-outcomes-v1',
  outcome_type: 'derived_unordered_podium_set_distribution',
  race_id: 1128,
  year: 2024,
  experiment_id: 'EXP-007',
  model_version: 'EXP-007+podium-count-v1',
  diagnostics: {
    method: 'maximum_entropy_fixed_size',
    driver_count: 20,
    podium_size: 3,
    combination_count: 1140,
    probability_sum: 1,
    reconstructed_marginal_sum: 3,
    maximum_marginal_error: 3.8e-13,
    entropy_bits: 7.891,
    effective_outcome_count: 237.6,
    returned_outcome_count: 3,
    returned_probability_sum: 0.55,
  },
  outcomes: [
    {
      rank: 1,
      driver_ids: [832, 844, 857],
      probability: 0.24,
      cumulative_probability: 0.24,
    },
    {
      rank: 2,
      driver_ids: [830, 844, 857],
      probability: 0.18,
      cumulative_probability: 0.42,
    },
    {
      rank: 3,
      driver_ids: [830, 832, 844],
      probability: 0.13,
      cumulative_probability: 0.55,
    },
  ],
  driver_marginals: [
    {
      driver_id: 844,
      forecast_rank: 1,
      released_probability: 0.8,
      reconstructed_probability: 0.8,
      absolute_error: 0,
    },
  ],
  co_podium_pairs: [
    { rank: 1, driver_ids: [844, 857], probability: 0.51 },
    { rank: 2, driver_ids: [832, 844], probability: 0.46 },
  ],
  evidence_boundary: {
    derived_from: 'released race-level marginal podium probabilities',
    outcome_data_used: false,
    separately_trained_joint_model: false,
    joint_forecast_validated: false,
    causal: false,
    ordering: 'unordered_podium_set',
    statement:
      'This maximum-entropy distribution is derived from released marginals; it is not a separately trained or validated finishing-order forecast.',
  },
  notes: ['Every outcome contains three distinct drivers.'],
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it('lazily builds and explains an accessible podium outcome map', async () => {
  const fetch = vi.fn(async (url) => {
    if (url.includes('podium-outcomes')) return { ok: true, json: async () => outcomeMap };
    return { ok: true, json: async () => grid };
  });
  vi.stubGlobal('fetch', fetch);

  render(<PodiumOutcomeLab raceId="1128" year={2024} />);

  const buildButton = await screen.findByRole('button', { name: 'Build outcome map' });
  expect(screen.getByRole('heading', { name: 'Podium outcome lab' })).toBeInTheDocument();
  expect(screen.getByText(/from individual chances to complete podium sets/i)).toBeInTheDocument();
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(fetch).toHaveBeenCalledWith('/api/races/1128/grid', expect.any(Object));

  fireEvent.click(buildButton);

  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
  expect(fetch).toHaveBeenLastCalledWith(
    '/api/predictions/1128/podium-outcomes?limit=12',
    expect.any(Object),
  );
  expect(await screen.findByText('1,140')).toBeInTheDocument();
  expect(screen.getByText('237.6')).toBeInTheDocument();
  expect(screen.getByText('55.0%')).toBeInTheDocument();
  expect(screen.getByText('3.80e-13')).toBeInTheDocument();
  expect(screen.getByRole('status')).toHaveTextContent(
    'Outcome map ready. 1,140 complete sets calculated; showing 3.',
  );

  const outcomes = screen.getByRole('list', { name: 'Most likely unordered podium sets' });
  const firstOutcome = within(outcomes).getAllByRole('listitem')[0];
  expect(within(firstOutcome).getByText('Charles Leclerc')).toBeInTheDocument();
  expect(within(firstOutcome).getByText('Oscar Piastri')).toBeInTheDocument();
  expect(within(firstOutcome).getByText('Carlos Sainz')).toBeInTheDocument();
  expect(within(firstOutcome).getByText('24.0%')).toBeInTheDocument();
  expect(within(firstOutcome).getByText(/cumulative 24.0%/i)).toBeInTheDocument();

  const pairs = screen.getByRole('list', { name: 'Most likely co-podium pairs' });
  expect(within(pairs).getByText('Charles Leclerc + Oscar Piastri')).toBeInTheDocument();
  expect(within(pairs).getByText('51.0%')).toBeInTheDocument();
  expect(screen.getByText('Unordered three-driver sets')).toBeInTheDocument();
  expect(
    screen.getByText(/not a separately trained or validated finishing-order forecast/i),
  ).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Clear outcome map' }));
  expect(screen.queryByRole('list', { name: 'Most likely unordered podium sets' })).toBeNull();
});

it('shows a bounded request error and can retry', async () => {
  let outcomeCalls = 0;
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url) => {
      if (!url.includes('podium-outcomes')) return { ok: true, json: async () => grid };
      outcomeCalls += 1;
      if (outcomeCalls === 1)
        return {
          ok: false,
          status: 503,
          json: async () => ({ detail: 'Podium outcome distribution could not be derived.' }),
        };
      return { ok: true, json: async () => outcomeMap };
    }),
  );

  render(<PodiumOutcomeLab raceId="1128" year={2024} />);
  fireEvent.click(await screen.findByRole('button', { name: 'Build outcome map' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('could not be derived');
  fireEvent.click(screen.getByRole('button', { name: 'Try outcome map again' }));
  expect(
    await screen.findByRole('list', { name: 'Most likely unordered podium sets' }),
  ).toBeInTheDocument();
  expect(outcomeCalls).toBe(2);
});

it('resets derived results when the selected race changes', async () => {
  const fetch = vi.fn(async (url) => {
    if (url.includes('podium-outcomes')) return { ok: true, json: async () => outcomeMap };
    return { ok: true, json: async () => grid };
  });
  vi.stubGlobal('fetch', fetch);

  const view = render(<PodiumOutcomeLab raceId="1128" year={2024} />);
  fireEvent.click(await screen.findByRole('button', { name: 'Build outcome map' }));
  expect(
    await screen.findByRole('list', { name: 'Most likely unordered podium sets' }),
  ).toBeInTheDocument();

  view.rerender(<PodiumOutcomeLab raceId="1129" year={2024} />);

  await waitFor(() =>
    expect(screen.queryByRole('list', { name: 'Most likely unordered podium sets' })).toBeNull(),
  );
  expect(fetch).toHaveBeenCalledWith('/api/races/1129/grid', expect.any(Object));
});

it('explains the supported evaluation window without fetching older races', () => {
  const fetch = vi.fn();
  vi.stubGlobal('fetch', fetch);

  render(<PodiumOutcomeLab raceId="900" year={2021} />);

  expect(
    screen.getByText(/outcome maps begin with the 2022 evaluation window/i),
  ).toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();
});
