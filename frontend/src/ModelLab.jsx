import React from 'react';
import { Link } from 'react-router-dom';
import { useApi } from './api';

const metricLabels = {
  log_loss: 'Log loss',
  brier_score: 'Brier score',
  top3_hit_rate: 'Top-three hit rate',
  ece_10_bins: 'Calibration error',
};
const featureLabels = {
  grid_position: 'Recorded starting grid',
  driver_recent_podium: 'Driver podium rate, previous five starts',
  driver_recent_finish: 'Driver classification, previous five starts',
  driver_recent_dnf: 'Driver nonfinish rate, previous five starts',
  constructor_recent_podium: 'Constructor podium rate, previous five races',
  driver_circuit_podium: 'Driver podium history at this circuit',
  driver_career_podium: 'Driver career podium rate with prior smoothing',
};

const fixed = (value, digits = 6) => Number(value).toFixed(digits);
const range = (interval) => `${fixed(interval.lower_95)} to ${fixed(interval.upper_95)}`;
const shortHash = (value) => `${value.slice(0, 12)}…`;

function TemporalTrack({ split }) {
  return (
    <div className="temporal-track" aria-label="Temporal model evaluation split">
      {[
        ['Train', split.training_years, 'Model fit'],
        ['Selection', split.selection_years, 'Choice + calibration'],
        ['Evaluation', split.inference_years, 'Consumed test'],
      ].map(([label, years, note]) => (
        <div key={label}>
          <span>{label}</span>
          <b>
            {years[0]}—{years[1]}
          </b>
          <small>{note}</small>
        </div>
      ))}
    </div>
  );
}

function ScoreTable({ metrics }) {
  const rows = [];
  for (const [splitName, split] of Object.entries(metrics)) {
    for (const metric of Object.keys(metricLabels)) {
      rows.push({ splitName, split, metric });
    }
  }
  return (
    <div className="table-scroll model-score-table">
      <table aria-label="Model score comparison">
        <thead>
          <tr>
            <th scope="col">Period</th>
            <th scope="col">Measure</th>
            <th scope="col">Raw model</th>
            <th scope="col">Projected model</th>
            <th scope="col">Projected grid baseline</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ splitName, split, metric }, index) => (
            <tr key={`${splitName}-${metric}`}>
              <td>{index % 4 === 0 ? `${split.years[0]}—${split.years[1]}` : ''}</td>
              <td>{metricLabels[metric]}</td>
              <td>{fixed(split.selected_model.raw[metric])}</td>
              <td className="model-score-selected">
                {fixed(split.selected_model.projected[metric])}
              </td>
              <td>{fixed(split.baseline.projected[metric])}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CalibrationBar({ label, value }) {
  return (
    <div className="calibration-row">
      <span>{label}</span>
      <span className="calibration-track" aria-hidden="true">
        <span style={{ width: `${Math.min(100, value * 2000)}%` }} />
      </span>
      <b>{fixed(value, 4)}</b>
    </div>
  );
}

function LoadedModelLab({ card }) {
  const constraint = card.metrics.consumed_test.race_constraint;
  const bootstrap = card.paired_race_bootstrap.metrics;
  return (
    <article className="model-lab">
      <Link className="back" to="/">
        ← Return to championship archive
      </Link>
      <header className="model-hero">
        <div>
          <p className="eyebrow">Model accountability / Verified release evidence</p>
          <h1>Every forecast leaves a trail.</h1>
          <p className="lede">
            Inspect what the podium model sees, when it learned, how its probabilities are
            corrected, and where the evidence stops.
          </p>
        </div>
        <div className="model-identity">
          <span>Release</span>
          <b>EXP / 007</b>
          <code>{card.identity.model_version}</code>
          <small>Manifest and evidence hashes verified</small>
        </div>
      </header>

      <section className="model-section" aria-labelledby="split-title">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Temporal discipline</p>
            <h2 id="split-title">One direction through time</h2>
          </div>
          <span>Later outcomes never train an earlier forecast</span>
        </div>
        <TemporalTrack split={card.temporal_split} />
        <p className="evidence-warning">{card.evidence_boundary.statement}</p>
      </section>

      <section className="constraint-section" aria-labelledby="constraint-title">
        <div className="constraint-number" aria-hidden="true">
          3
        </div>
        <div>
          <p className="eyebrow">Probability scrutineering</p>
          <h2 id="constraint-title">Three podium places. Three expected podiums.</h2>
          <p>
            One equal log-odds shift brings each race’s marginal probabilities to the known total.
            It reads no finish data and preserves the driver order.
          </p>
        </div>
        <dl className="constraint-readout">
          <div>
            <dt>Selected model</dt>
            <dd>
              {constraint.selected_average_raw_sum.toFixed(3)} →{' '}
              {constraint.selected_average_projected_sum.toFixed(3)}
            </dd>
          </div>
          <div>
            <dt>Maximum sum error</dt>
            <dd>{constraint.maximum_absolute_sum_error.toExponential(2)}</dd>
          </div>
          <div>
            <dt>Ranking</dt>
            <dd>Preserved</dd>
          </div>
        </dl>
      </section>

      <section className="model-section" aria-labelledby="scores-title">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Score sheet</p>
            <h2 id="scores-title">Before and after projection</h2>
          </div>
          <span>Lower log loss, Brier, and calibration error are better</span>
        </div>
        <ScoreTable metrics={card.metrics} />
      </section>

      <div className="model-two-column">
        <section className="model-section bootstrap-section" aria-labelledby="uncertainty-title">
          <p className="eyebrow">Whole-race bootstrap / 5,000 draws</p>
          <h2 id="uncertainty-title">What uncertainty says</h2>
          <dl>
            <div>
              <dt>Log loss difference</dt>
              <dd>{range(bootstrap.log_loss)}</dd>
            </div>
            <div>
              <dt>Brier difference</dt>
              <dd>{range(bootstrap.brier_score)}</dd>
            </div>
            <div>
              <dt>Top-three hit difference</dt>
              <dd>{range(bootstrap.top3_hit_rate)}</dd>
            </div>
          </dl>
          <p>{card.paired_race_bootstrap.limitation}</p>
        </section>
        <section className="model-section" aria-labelledby="calibration-title">
          <p className="eyebrow">Probability reliability</p>
          <h2 id="calibration-title">Calibration check</h2>
          <p>
            Ten-bin calibration error compares forecast confidence with the observed podium rate.
          </p>
          <CalibrationBar label="Validation · raw" value={card.calibration.validation_raw_ece} />
          <CalibrationBar
            label="Validation · projected"
            value={card.calibration.validation_projected_ece}
          />
          <CalibrationBar label="Test · raw" value={card.calibration.consumed_test_raw_ece} />
          <CalibrationBar
            label="Test · projected"
            value={card.calibration.consumed_test_projected_ece}
          />
        </section>
      </div>

      <section className="model-section" aria-labelledby="seasons-title">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Season ledger</p>
            <h2 id="seasons-title">Performance by year</h2>
          </div>
          <span>Projected probabilities</span>
        </div>
        <div className="table-scroll">
          <table aria-label="Projected model scores by season">
            <thead>
              <tr>
                <th scope="col">Season</th>
                <th scope="col">Races</th>
                <th scope="col">Log loss</th>
                <th scope="col">Brier</th>
                <th scope="col">Top-three hit rate</th>
                <th scope="col">Evidence status</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(card.per_season).map(([year, season]) => (
                <tr key={year}>
                  <td>{year}</td>
                  <td>{season.races}</td>
                  <td>{fixed(season.selected_model.log_loss)}</td>
                  <td>{fixed(season.selected_model.brier_score)}</td>
                  <td>{fixed(season.selected_model.top3_hit_rate)}</td>
                  <td>
                    {season.evidence_status === 'consumed_post_test_iterative'
                      ? 'Consumed test'
                      : 'Reused selection'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <div className="model-two-column model-details">
        <section className="model-section" aria-labelledby="inputs-title">
          <p className="eyebrow">Input register</p>
          <h2 id="inputs-title">What the model sees</h2>
          <ol className="feature-register">
            {card.features.map((feature) => (
              <li key={feature}>
                <span>{featureLabels[feature] || feature}</span>
                <code>{feature}</code>
              </li>
            ))}
          </ol>
          <p className="caption">
            Explanations use {card.explanations.method} in {card.explanations.units}. They describe
            fitted associations and are not causal.
          </p>
        </section>
        <section className="model-section" aria-labelledby="lineage-title">
          <p className="eyebrow">Chain of custody</p>
          <h2 id="lineage-title">Artifact lineage</h2>
          <dl className="hash-register">
            <div>
              <dt>Selected model</dt>
              <dd>
                <code title={card.lineage.artifacts.selected_model}>
                  {shortHash(card.lineage.artifacts.selected_model)}
                </code>
              </dd>
            </div>
            <div>
              <dt>Grid baseline</dt>
              <dd>
                <code title={card.lineage.artifacts.grid_baseline}>
                  {shortHash(card.lineage.artifacts.grid_baseline)}
                </code>
              </dd>
            </div>
            <div>
              <dt>Projection evidence</dt>
              <dd>
                <code title={card.lineage.evidence.race_constraint_evaluation}>
                  {shortHash(card.lineage.evidence.race_constraint_evaluation)}
                </code>
              </dd>
            </div>
          </dl>
          <p className="caption">
            The service checks these hashes before model deserialization and refuses readiness on a
            mismatch.
          </p>
        </section>
      </div>

      <div className="model-two-column model-uses">
        <section aria-labelledby="intended-title">
          <h2 id="intended-title">Designed for</h2>
          <ul>
            {card.intended_use.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
        <section aria-labelledby="excluded-title">
          <h2 id="excluded-title">Outside scope</h2>
          <ul>
            {card.excluded_uses.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      </div>

      <section className="model-section limitations" aria-labelledby="limits-title">
        <p className="eyebrow">Read before use</p>
        <h2 id="limits-title">Known limits</h2>
        <ul>
          {card.limitations.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>
    </article>
  );
}

export default function ModelLab() {
  const state = useApi('/model-card');
  if (state.loading)
    return (
      <div className="state model-page-state" role="status">
        Verifying model evidence…
      </div>
    );
  if (state.error)
    return (
      <div className="state error model-page-state" role="alert">
        {state.error}
      </div>
    );
  return <LoadedModelLab card={state.data} />;
}
