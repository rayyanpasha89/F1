import React from 'react';
import { cleanup, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import ModelLab from './ModelLab';

const scores = (logLoss, brier, top3, ece) => ({
  log_loss: logLoss,
  brier_score: brier,
  roc_auc: 0.93,
  top3_hit_rate: top3,
  exact_podium_set_rate: 0.2,
  ece_10_bins: ece,
});
const comparison = (raw, projected, baseline = false) => ({
  raw,
  projected,
  projected_minus_raw: {
    log_loss: projected.log_loss - raw.log_loss,
    brier_score: projected.brier_score - raw.brier_score,
    top3_hit_rate: 0,
  },
  baseline,
});
const constraint = {
  expected_podiums: 3,
  selected_average_raw_sum: 2.98,
  selected_average_projected_sum: 3,
  baseline_average_raw_sum: 2.99,
  baseline_average_projected_sum: 3,
  maximum_absolute_sum_error: 8.88e-16,
  selected_rank_preserved: true,
  baseline_rank_preserved: true,
};
const card = {
  schema_version: 'f1-public-model-card-v1',
  identity: {
    name: 'F1 Race Strategist podium probability model',
    model_version: 'EXP-007+podium-count-v1',
    experiment_id: 'EXP-007',
  },
  lineage: {
    manifest_generated_at: '2026-09-10T00:00:00Z',
    selection_frozen_at: '2026-09-08T00:00:00Z',
    artifacts: { selected_model: 'a'.repeat(64), grid_baseline: 'b'.repeat(64) },
    evidence: {
      model_selection: 'c'.repeat(64),
      final_test_metrics: 'd'.repeat(64),
      data_audit: 'e'.repeat(64),
      race_constraint_evaluation: 'f'.repeat(64),
    },
  },
  source_coverage: { archive_years: [1950, 2024], races: 1125, audited_tables: 14 },
  intended_use: ['Explore historical podium probabilities.', 'Teach temporal evaluation.'],
  excluded_uses: ['Live race operations.', 'Betting or financial decisions.'],
  features: ['grid_position', 'driver_recent_podium', 'constructor_recent_podium'],
  temporal_split: {
    training_years: [2010, 2018],
    selection_years: [2019, 2021],
    inference_years: [2022, 2024],
  },
  postprocessor: { name: 'race_logit_offset', version: 'v1', expected_count: 3 },
  metrics: {
    validation: {
      years: [2019, 2021],
      evidence_status: 'reused_model_selection_period',
      rows: 1200,
      races: 60,
      selected_model: comparison(
        scores(0.209557, 0.062173, 0.727778, 0.0204),
        scores(0.208772, 0.062043, 0.727778, 0.019),
      ),
      baseline: comparison(
        scores(0.246224, 0.069488, 0.716667, 0.0348),
        scores(0.24622, 0.069481, 0.716667, 0.0347),
        true,
      ),
      race_constraint: constraint,
    },
    consumed_test: {
      years: [2022, 2024],
      evidence_status: 'consumed_post_test_iterative',
      rows: 1359,
      races: 68,
      selected_model: comparison(
        scores(0.219846, 0.069285, 0.647059, 0.0146),
        scores(0.218918, 0.069044, 0.647059, 0.0141),
      ),
      baseline: comparison(
        scores(0.249898, 0.073811, 0.651961, 0.0203),
        scores(0.249804, 0.073772, 0.651961, 0.0202),
        true,
      ),
      race_constraint: constraint,
    },
  },
  per_season: Object.fromEntries(
    [2019, 2020, 2021, 2022, 2023, 2024].map((year) => [
      year,
      {
        evidence_status:
          year < 2022 ? 'reused_model_selection_period' : 'consumed_post_test_iterative',
        rows: 400,
        races: 20,
        selected_model: scores(0.21, 0.065, 0.68, 0.02),
        baseline: scores(0.25, 0.075, 0.65, 0.03),
      },
    ]),
  ),
  paired_race_bootstrap: {
    split: 'consumed_test',
    unit: 'whole_race',
    replicates: 5000,
    seed: 42,
    comparison: 'projected_selected_minus_projected_baseline',
    metrics: {
      log_loss: { estimate: -0.030886, lower_95: -0.049274, upper_95: -0.013971 },
      brier_score: { estimate: -0.004727, lower_95: -0.00849, upper_95: -0.000895 },
      top3_hit_rate: { estimate: -0.004902, lower_95: -0.034314, upper_95: 0.02451 },
    },
    limitation: 'Intervals do not create an unseen holdout.',
  },
  calibration: {
    method: 'temporal training OOF sigmoid',
    slope: 1.1117,
    intercept: 0.1615,
    validation_raw_ece: 0.0204,
    validation_projected_ece: 0.019,
    consumed_test_raw_ece: 0.0146,
    consumed_test_projected_ece: 0.0141,
  },
  explanations: { method: 'Tree SHAP', units: 'calibrated log-odds', causal: false },
  evidence_boundary: {
    status: 'post_test_iterative_evidence',
    unseen_holdout: false,
    statement: 'The 2022–2024 outcomes were already consumed before this assessment.',
  },
  limitations: [
    'Historical snapshot through 2024.',
    'Weather and live telemetry are outside the model.',
  ],
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it('renders temporal splits, before-after metrics, uncertainty, and lineage', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => card }));

  render(
    <MemoryRouter>
      <ModelLab />
    </MemoryRouter>,
  );

  expect(
    await screen.findByRole('heading', { name: 'Every forecast leaves a trail.' }),
  ).toBeInTheDocument();
  expect(screen.getByText('EXP-007+podium-count-v1')).toBeInTheDocument();
  expect(screen.getByText('Train')).toBeInTheDocument();
  expect(screen.getByText('2010—2018')).toBeInTheDocument();
  expect(screen.getByText('Selection')).toBeInTheDocument();
  expect(screen.getByText('Evaluation')).toBeInTheDocument();
  const metricTable = screen.getByRole('table', { name: 'Model score comparison' });
  expect(within(metricTable).getByText('0.219846')).toBeInTheDocument();
  expect(within(metricTable).getByText('0.218918')).toBeInTheDocument();
  expect(screen.getByText('-0.049274 to -0.013971')).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Calibration check' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Artifact lineage' })).toBeInTheDocument();
  expect(screen.getByText('aaaaaaaaaaaa…')).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Known limits' })).toBeInTheDocument();
  expect(screen.getByText(/already consumed/i)).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /return to championship archive/i })).toHaveAttribute(
    'href',
    '/',
  );
});

it('renders explicit loading and failure states', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => new Promise(() => {})),
  );
  const first = render(
    <MemoryRouter>
      <ModelLab />
    </MemoryRouter>,
  );
  expect(screen.getByRole('status')).toHaveTextContent('Verifying model evidence');
  first.unmount();

  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({ detail: 'Model accountability evidence unavailable.' }),
    }),
  );
  render(
    <MemoryRouter>
      <ModelLab />
    </MemoryRouter>,
  );
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Model accountability evidence unavailable',
  );
});
