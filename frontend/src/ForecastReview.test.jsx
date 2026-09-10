import React from 'react';
import { cleanup, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import ForecastReview from './ForecastReview';

const review = {
  review_type: 'post_race_review',
  race: { race_id: 1128, year: 2024, name: 'Monaco Grand Prix' },
  model_version: 'EXP-007+podium-count-v1',
  postprocessor: { method: 'race_logit_offset', expected_podiums: 3 },
  predicted_podium: [
    {
      rank: 1,
      driver_id: 844,
      driver_name: 'Charles Leclerc',
      constructor_name: 'Ferrari',
      probability: 0.7394,
    },
    {
      rank: 2,
      driver_id: 857,
      driver_name: 'Oscar Piastri',
      constructor_name: 'McLaren',
      probability: 0.5863,
    },
    {
      rank: 3,
      driver_id: 832,
      driver_name: 'Carlos Sainz',
      constructor_name: 'Ferrari',
      probability: 0.5207,
    },
  ],
  recorded_podium: [
    {
      rank: 1,
      driver_id: 844,
      driver_name: 'Charles Leclerc',
      constructor_name: 'Ferrari',
      probability: 0.7394,
    },
    {
      rank: 2,
      driver_id: 857,
      driver_name: 'Oscar Piastri',
      constructor_name: 'McLaren',
      probability: 0.5863,
    },
    {
      rank: 3,
      driver_id: 832,
      driver_name: 'Carlos Sainz',
      constructor_name: 'Ferrari',
      probability: 0.5207,
    },
  ],
  top_three_hits: 3,
  exact_podium_set: true,
  brier_score: 0.0446527,
  mean_absolute_error: 0.1153569,
  surprises: {
    largest_overprediction: { driver_name: 'Lando Norris', probability: 0.41, error: 0.41 },
    largest_underprediction: { driver_name: 'Carlos Sainz', probability: 0.5207, error: 0.4793 },
  },
  drivers: [
    {
      predicted_rank: 1,
      driver_id: 844,
      driver_name: 'Charles Leclerc',
      constructor_name: 'Ferrari',
      grid: 1,
      probability: 0.7394,
      recorded_finish: '1',
      recorded_podium: true,
      absolute_error: 0.2606,
    },
    {
      predicted_rank: 4,
      driver_id: 846,
      driver_name: 'Lando Norris',
      constructor_name: 'McLaren',
      grid: 4,
      probability: 0.41,
      recorded_finish: '4',
      recorded_podium: false,
      absolute_error: 0.41,
    },
  ],
  notes: ['Recorded finishes are evaluation labels only and are never model inputs.'],
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it('renders the post-race forecast review with clear metric semantics', async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => review });
  vi.stubGlobal('fetch', fetch);

  render(
    <MemoryRouter>
      <ForecastReview raceId="1128" year={2024} />
    </MemoryRouter>,
  );

  expect(await screen.findByRole('heading', { name: 'Forecast vs reality' })).toBeInTheDocument();
  expect(screen.getByText('Post-race review')).toBeInTheDocument();
  expect(screen.getByText('3 / 3')).toBeInTheDocument();
  expect(screen.getByText('Exact podium set')).toBeInTheDocument();
  expect(screen.getByText('0.0447')).toBeInTheDocument();
  expect(screen.getByText(/Brier score averages squared probability error/i)).toBeInTheDocument();
  const forecast = screen.getByRole('list', { name: 'Predicted podium' });
  const recorded = screen.getByRole('list', { name: 'Recorded podium' });
  expect(within(forecast).getByText('Charles Leclerc')).toBeInTheDocument();
  expect(within(recorded).getByText('Carlos Sainz')).toBeInTheDocument();
  expect(screen.getByText(/largest overprediction/i)).toBeInTheDocument();
  expect(screen.getAllByText('Lando Norris')).toHaveLength(2);
  expect(screen.getByRole('link', { name: /open model accountability/i })).toHaveAttribute(
    'href',
    '/model',
  );
  expect(fetch).toHaveBeenCalledWith('/api/predictions/1128/review', expect.any(Object));
});

it('renders loading, unavailable, and safe error states', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => new Promise(() => {})),
  );
  const { unmount } = render(
    <MemoryRouter>
      <ForecastReview raceId="1128" year={2024} />
    </MemoryRouter>,
  );
  expect(screen.getByRole('status')).toHaveTextContent('Building the post-race review');
  unmount();

  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      json: async () => ({ detail: 'Recorded podium is unavailable for this race.' }),
    }),
  );
  const result = render(
    <MemoryRouter>
      <ForecastReview raceId="1128" year={2024} />
    </MemoryRouter>,
  );
  expect(await screen.findByRole('alert')).toHaveTextContent('Recorded podium is unavailable');
  result.unmount();

  render(
    <MemoryRouter>
      <ForecastReview raceId="900" year={2021} />
    </MemoryRouter>,
  );
  expect(screen.getByText(/reviews begin with the 2022 evaluation window/i)).toBeInTheDocument();
});
