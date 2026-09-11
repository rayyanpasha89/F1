import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import GridScenarioLab from './GridScenarioLab';

const grid = {
  data: [
    { driver_id: 844, driver_name: 'Charles Leclerc', grid: 1 },
    { driver_id: 857, driver_name: 'Oscar Piastri', grid: 2 },
    { driver_id: 832, driver_name: 'Carlos Sainz', grid: 3 },
    { driver_id: 830, driver_name: 'Max Verstappen', grid: 4 },
  ],
};

const scenario = {
  schema_version: 'f1-grid-scenario-v1',
  scenario_type: 'counterfactual_grid_swap',
  race_id: 1128,
  year: 2024,
  experiment_id: 'EXP-007',
  model_version: 'EXP-007+podium-count-v1',
  modification: {
    kind: 'swap_recorded_grid_positions',
    drivers: [
      {
        driver_id: 832,
        recorded_grid_position: 3,
        scenario_grid_position: 2,
        original_grid_input: 3,
        scenario_grid_input: 2,
      },
      {
        driver_id: 857,
        recorded_grid_position: 2,
        scenario_grid_position: 3,
        original_grid_input: 2,
        scenario_grid_input: 3,
      },
    ],
  },
  postprocessing: {
    method: 'race_logit_offset',
    expected_podiums: 3,
    original_sum: 3,
    scenario_sum: 3,
  },
  predictions: [
    {
      driver_id: 830,
      constructor_id: 3,
      recorded_grid_position: 4,
      scenario_grid_position: 4,
      original_grid_input: 4,
      scenario_grid_input: 4,
      scenario_rank: 1,
      original_rank: 1,
      original_probability: 0.9,
      scenario_probability: 0.9,
      probability_delta: 0,
      starting_grid_contribution: { original: 0.05, scenario: 0.05, delta: 0 },
    },
    {
      driver_id: 844,
      constructor_id: 2,
      recorded_grid_position: 1,
      scenario_grid_position: 1,
      original_grid_input: 1,
      scenario_grid_input: 1,
      original_rank: 2,
      scenario_rank: 2,
      original_probability: 0.8,
      scenario_probability: 0.8,
      probability_delta: 0,
      starting_grid_contribution: { original: 0.4, scenario: 0.4, delta: 0 },
    },
    {
      driver_id: 832,
      constructor_id: 2,
      recorded_grid_position: 3,
      scenario_grid_position: 2,
      original_grid_input: 3,
      scenario_grid_input: 2,
      original_rank: 4,
      scenario_rank: 3,
      original_probability: 0.6,
      scenario_probability: 0.7,
      probability_delta: 0.1,
      starting_grid_contribution: { original: 0.1, scenario: 0.2, delta: 0.1 },
    },
    {
      driver_id: 857,
      constructor_id: 1,
      recorded_grid_position: 2,
      scenario_grid_position: 3,
      original_grid_input: 2,
      scenario_grid_input: 3,
      original_rank: 3,
      scenario_rank: 4,
      original_probability: 0.7,
      scenario_probability: 0.6,
      probability_delta: -0.1,
      starting_grid_contribution: { original: 0.2, scenario: 0.1, delta: -0.1 },
    },
  ],
  evidence_boundary: {
    input_scope: 'recorded pre-race features with two grid positions swapped',
    outcome_data_used: false,
    causal: false,
    validated_forecast: false,
    statement:
      'This counterfactual shows frozen-model sensitivity; it is not a causal estimate, an unseen evaluation, or a live-race recommendation.',
  },
  notes: ['Only the two selected model grid inputs changed.'],
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it('runs an accessible two-driver grid swap and renders the full comparison', async () => {
  const fetch = vi.fn(async (url, options = {}) => {
    if (options.method === 'POST') return { ok: true, json: async () => scenario };
    return { ok: true, json: async () => grid };
  });
  vi.stubGlobal('fetch', fetch);

  render(<GridScenarioLab raceId="1128" year={2024} />);

  const first = await screen.findByRole('combobox', { name: 'First driver' });
  expect(screen.getByRole('heading', { name: 'Grid swap lab' })).toBeInTheDocument();
  const second = screen.getByRole('combobox', { name: 'Second driver' });
  expect(first).toHaveValue('844');
  expect(second).toHaveValue('857');
  fireEvent.change(first, { target: { value: '832' } });
  fireEvent.click(screen.getByRole('button', { name: 'Run grid swap' }));

  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
  expect(fetch).toHaveBeenLastCalledWith(
    '/api/predictions/1128/scenario',
    expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ driver_a_id: 832, driver_b_id: 857 }),
    }),
  );
  expect(await screen.findByText('Frozen-model sensitivity')).toBeInTheDocument();
  expect(screen.getByText('+10.0 pp')).toBeInTheDocument();
  expect(screen.getByText('−10.0 pp')).toBeInTheDocument();
  const table = screen.getByRole('table', { name: 'Grid swap probability comparison' });
  expect(within(table).getByText('Oscar Piastri')).toBeInTheDocument();
  expect(within(table).getByText('Carlos Sainz')).toBeInTheDocument();
  expect(screen.getByText(/not a causal estimate/i)).toBeInTheDocument();
  expect(screen.getByText(/3.000 podium places/i)).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Reset scenario' }));
  expect(screen.queryByRole('table', { name: 'Grid swap probability comparison' })).toBeNull();
});

it('disables invalid swaps and renders a bounded API error', async () => {
  let calls = 0;
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_url, options = {}) => {
      calls += 1;
      if (!options.method) return { ok: true, json: async () => grid };
      return {
        ok: false,
        status: 422,
        json: async () => ({ detail: 'Both drivers must be starters in this race.' }),
      };
    }),
  );

  render(<GridScenarioLab raceId="1128" year={2024} />);
  const first = await screen.findByRole('combobox', { name: 'First driver' });
  const second = screen.getByRole('combobox', { name: 'Second driver' });
  fireEvent.change(second, { target: { value: first.value } });
  expect(screen.getByRole('button', { name: 'Run grid swap' })).toBeDisabled();
  fireEvent.change(second, { target: { value: '857' } });
  fireEvent.click(screen.getByRole('button', { name: 'Run grid swap' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Both drivers must be starters');
  expect(calls).toBe(2);
});

it('explains the supported evaluation window without fetching older races', () => {
  const fetch = vi.fn();
  vi.stubGlobal('fetch', fetch);

  render(<GridScenarioLab raceId="900" year={2021} />);

  expect(screen.getByText(/scenarios begin with the 2022 evaluation window/i)).toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();
});
