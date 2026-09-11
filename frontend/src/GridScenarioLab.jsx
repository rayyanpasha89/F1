import React, { useState } from 'react';
import { request, useApi } from './api';

const percent = (value) => `${(value * 100).toFixed(1)}%`;

const probabilityDelta = (value) => {
  const points = value * 100;
  if (Math.abs(points) < 0.05) return '0.0 pp';
  return `${points > 0 ? '+' : '−'}${Math.abs(points).toFixed(1)} pp`;
};

const contributionDelta = (value) => {
  if (Math.abs(value) < 0.0005) return '0.000';
  return `${value > 0 ? '+' : '−'}${Math.abs(value).toFixed(3)}`;
};

const gridLabel = (position) => (position > 0 ? `P${position}` : 'Pit lane');

function DriverSelect({ id, label, value, options, onChange }) {
  return (
    <label htmlFor={id}>
      <span>{label}</span>
      <select id={id} aria-label={label} value={value} onChange={onChange}>
        {options.map((driver) => (
          <option key={driver.driver_id} value={driver.driver_id}>
            {gridLabel(driver.grid)} · {driver.driver_name}
          </option>
        ))}
      </select>
    </label>
  );
}

function SupportedGridScenarioLab({ raceId }) {
  const gridState = useApi(`/races/${raceId}/grid`);
  const [driverA, setDriverA] = useState('');
  const [driverB, setDriverB] = useState('');
  const [scenario, setScenario] = useState(null);
  const [error, setError] = useState('');
  const [running, setRunning] = useState(false);

  const clearResult = () => {
    setScenario(null);
    setError('');
  };

  if (gridState.loading)
    return (
      <section className="grid-scenario-lab scenario-state" aria-labelledby="scenario-title">
        <p className="eyebrow">Counterfactual simulator</p>
        <h2 id="scenario-title">Grid swap lab</h2>
        <p role="status">Loading the recorded starting grid…</p>
      </section>
    );
  if (gridState.error)
    return (
      <section className="grid-scenario-lab scenario-state" aria-labelledby="scenario-title">
        <p className="eyebrow">Counterfactual simulator</p>
        <h2 id="scenario-title">Grid swap lab</h2>
        <p role="alert">{gridState.error}</p>
      </section>
    );

  const options = [...gridState.data.data].sort((a, b) => {
    const aGrid = a.grid > 0 ? a.grid : 99;
    const bGrid = b.grid > 0 ? b.grid : 99;
    return aGrid - bGrid || a.driver_id - b.driver_id;
  });
  if (options.length < 2)
    return (
      <section className="grid-scenario-lab scenario-state" aria-labelledby="scenario-title">
        <p className="eyebrow">Counterfactual simulator</p>
        <h2 id="scenario-title">Grid swap lab</h2>
        <p>At least two recorded starters are required.</p>
      </section>
    );

  const selectedA = driverA || String(options[0].driver_id);
  const selectedB = driverB || String(options[1].driver_id);
  const invalid = selectedA === selectedB;
  const names = Object.fromEntries(options.map((driver) => [driver.driver_id, driver.driver_name]));
  const changedIds = new Set(
    scenario?.modification.drivers.map((driver) => driver.driver_id) || [],
  );

  const runScenario = async (event) => {
    event.preventDefault();
    if (invalid || running) return;
    setRunning(true);
    setError('');
    setScenario(null);
    try {
      const result = await request(`/predictions/${raceId}/scenario`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          driver_a_id: Number(selectedA),
          driver_b_id: Number(selectedB),
        }),
      });
      setScenario(result);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setRunning(false);
    }
  };

  return (
    <section className="grid-scenario-lab" aria-labelledby="scenario-title">
      <div className="scenario-heading">
        <div>
          <p className="eyebrow">Counterfactual simulator</p>
          <h2 id="scenario-title">Grid swap lab</h2>
        </div>
        <span>Frozen-model sensitivity</span>
      </div>
      <p className="scenario-intro">
        Exchange two recorded starting positions and rerun the same verified model. Every other
        pre-race input stays fixed.
      </p>
      <div className="scenario-workbench">
        <form onSubmit={runScenario} className="scenario-controls">
          <DriverSelect
            id="scenario-driver-a"
            label="First driver"
            value={selectedA}
            options={options}
            onChange={(event) => {
              setDriverA(event.target.value);
              clearResult();
            }}
          />
          <div className="scenario-swap-mark" aria-hidden="true">
            ⇄
          </div>
          <DriverSelect
            id="scenario-driver-b"
            label="Second driver"
            value={selectedB}
            options={options}
            onChange={(event) => {
              setDriverB(event.target.value);
              clearResult();
            }}
          />
          {invalid && <p className="scenario-inline-error">Choose two different drivers.</p>}
          <div className="scenario-actions">
            <button type="submit" disabled={invalid || running}>
              {running ? 'Running model…' : 'Run grid swap'}
            </button>
            {(scenario || error) && (
              <button type="button" className="scenario-reset" onClick={clearResult}>
                Reset scenario
              </button>
            )}
          </div>
          <p className="scenario-control-note">
            Read-only · recorded grid inputs · no race outcomes
          </p>
        </form>

        <div className="scenario-explainer">
          <p className="eyebrow">What changes</p>
          <h3>One controlled model input</h3>
          <p>
            The two grid positions are exchanged. Driver form, constructor form, circuit history,
            calibration, and model weights remain fixed.
          </p>
          <p>
            The three-place race projection is recalculated, so small probability changes can appear
            across the full field.
          </p>
        </div>
      </div>

      {running && (
        <p role="status" className="scenario-status">
          Calculating the counterfactual…
        </p>
      )}
      {error && (
        <p role="alert" className="state error scenario-error">
          {error}
        </p>
      )}

      {scenario && (
        <div className="scenario-result" aria-live="polite">
          <div className="scenario-result-heading">
            <div>
              <p className="eyebrow">Scenario result</p>
              <h3>Probability movement across the grid</h3>
            </div>
            <div className="scenario-coherence">
              <b>{scenario.postprocessing.scenario_sum.toFixed(3)} podium places</b>
              <span>{scenario.model_version}</span>
            </div>
          </div>

          <div className="scenario-movers">
            {scenario.modification.drivers.map((change) => {
              const row = scenario.predictions.find(
                (prediction) => prediction.driver_id === change.driver_id,
              );
              return (
                <article key={change.driver_id}>
                  <span>
                    {gridLabel(change.recorded_grid_position)} →{' '}
                    {gridLabel(change.scenario_grid_position)}
                  </span>
                  <h4>{names[change.driver_id]}</h4>
                  <p>
                    {percent(row.original_probability)} → <b>{percent(row.scenario_probability)}</b>
                  </p>
                  <small>
                    Model rank {row.original_rank} → {row.scenario_rank}
                  </small>
                  <small>
                    Grid input {row.original_grid_input} → {row.scenario_grid_input}
                  </small>
                </article>
              );
            })}
          </div>

          <div className="table-scroll scenario-table">
            <table aria-label="Grid swap probability comparison">
              <thead>
                <tr>
                  <th scope="col">Scenario rank</th>
                  <th scope="col">Driver</th>
                  <th scope="col">Grid / model input</th>
                  <th scope="col">Released</th>
                  <th scope="col">Scenario</th>
                  <th scope="col">Probability Δ</th>
                  <th scope="col">Grid SHAP Δ</th>
                </tr>
              </thead>
              <tbody>
                {scenario.predictions.map((row) => (
                  <tr
                    key={row.driver_id}
                    className={changedIds.has(row.driver_id) ? 'scenario-changed' : ''}
                  >
                    <td data-label="Scenario rank">
                      <b>{row.scenario_rank}</b>
                      <small>was {row.original_rank}</small>
                    </td>
                    <td data-label="Driver">{names[row.driver_id]}</td>
                    <td data-label="Grid / model input">
                      {gridLabel(row.recorded_grid_position)} →{' '}
                      {gridLabel(row.scenario_grid_position)}
                      <small>
                        model {row.original_grid_input} → {row.scenario_grid_input}
                      </small>
                    </td>
                    <td data-label="Released">{percent(row.original_probability)}</td>
                    <td data-label="Scenario">
                      <b>{percent(row.scenario_probability)}</b>
                    </td>
                    <td
                      data-label="Probability change"
                      className={
                        row.probability_delta > 0
                          ? 'positive'
                          : row.probability_delta < 0
                            ? 'negative'
                            : ''
                      }
                    >
                      {probabilityDelta(row.probability_delta)}
                    </td>
                    <td data-label="Grid SHAP change">
                      {contributionDelta(row.starting_grid_contribution.delta)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="scenario-boundary">
            <b>Sensitivity analysis, with a strict boundary</b>
            <p>{scenario.evidence_boundary.statement}</p>
            <p>
              SHAP values use calibrated log-odds. They describe the frozen model’s associations;
              they do not predict the physical effect of changing a real starting position.
            </p>
          </div>
        </div>
      )}
    </section>
  );
}

export default function GridScenarioLab({ raceId, year }) {
  if (year < 2022)
    return (
      <section className="grid-scenario-lab scenario-state">
        <p className="eyebrow">Counterfactual simulator</p>
        <h2>Grid swap lab</h2>
        <p>Grid scenarios begin with the 2022 evaluation window.</p>
      </section>
    );
  return <SupportedGridScenarioLab raceId={raceId} />;
}
