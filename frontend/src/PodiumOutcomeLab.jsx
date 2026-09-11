import React, { useEffect, useRef, useState } from 'react';
import { request, useApi } from './api';

const percent = (value) => `${(value * 100).toFixed(1)}%`;

function SupportedPodiumOutcomeLab({ raceId }) {
  const gridState = useApi(`/races/${raceId}/grid`);
  const [outcomeMap, setOutcomeMap] = useState(null);
  const [error, setError] = useState('');
  const [running, setRunning] = useState(false);
  const requestVersion = useRef(0);

  useEffect(() => {
    requestVersion.current += 1;
    setOutcomeMap(null);
    setError('');
    setRunning(false);
  }, [raceId]);

  const clear = () => {
    requestVersion.current += 1;
    setOutcomeMap(null);
    setError('');
    setRunning(false);
  };

  const buildOutcomeMap = async () => {
    if (running) return;
    const version = ++requestVersion.current;
    setRunning(true);
    setError('');
    setOutcomeMap(null);
    try {
      const result = await request(`/predictions/${raceId}/podium-outcomes?limit=12`);
      if (requestVersion.current === version) setOutcomeMap(result);
    } catch (requestError) {
      if (requestVersion.current === version) setError(requestError.message);
    } finally {
      if (requestVersion.current === version) setRunning(false);
    }
  };

  if (gridState.loading)
    return (
      <section className="podium-outcome-lab outcome-state" aria-labelledby="outcome-title">
        <p className="eyebrow">Derived probability map</p>
        <h2 id="outcome-title">Podium outcome lab</h2>
        <p role="status">Loading the recorded driver field…</p>
      </section>
    );
  if (gridState.error)
    return (
      <section className="podium-outcome-lab outcome-state" aria-labelledby="outcome-title">
        <p className="eyebrow">Derived probability map</p>
        <h2 id="outcome-title">Podium outcome lab</h2>
        <p role="alert">{gridState.error}</p>
      </section>
    );

  const names = Object.fromEntries(
    gridState.data.data.map((driver) => [driver.driver_id, driver.driver_name]),
  );
  const driverName = (driverId) => names[driverId] || `Driver ${driverId}`;
  const topProbability = outcomeMap?.outcomes[0]?.probability || 1;

  return (
    <section className="podium-outcome-lab" aria-labelledby="outcome-title">
      <div className="outcome-heading">
        <div>
          <p className="eyebrow">Derived probability map</p>
          <h2 id="outcome-title">Podium outcome lab</h2>
        </div>
        <span>Maximum entropy · fixed size</span>
      </div>
      <p className="outcome-intro">
        Move from individual chances to complete podium sets. The lab finds the least-assumptive
        distribution that preserves every released driver probability and exactly three places.
      </p>

      {!outcomeMap && (
        <div className="outcome-primer">
          <div>
            <p className="eyebrow">The question</p>
            <h3>Which three drivers appear together?</h3>
            <p>
              The released model scores each driver separately. This derivation joins those scores
              into every possible unordered three-driver set without using the recorded result.
            </p>
            <ul>
              <li>Preserves all released podium probabilities</li>
              <li>Assigns one probability across the complete set space</li>
              <li>Adds no preference for unsupported driver interactions</li>
            </ul>
          </div>
          <div className="outcome-action">
            <span>Read-only derivation</span>
            <b>3 drivers</b>
            <small>per unordered outcome</small>
            <button type="button" onClick={buildOutcomeMap} disabled={running}>
              {running
                ? 'Building outcome map…'
                : error
                  ? 'Try outcome map again'
                  : 'Build outcome map'}
            </button>
            <p>No same-race labels · no model retraining</p>
          </div>
        </div>
      )}

      {running && (
        <p role="status" className="outcome-status">
          Solving the complete podium set distribution…
        </p>
      )}
      {error && (
        <p role="alert" className="state error outcome-error">
          {error}
        </p>
      )}

      {outcomeMap && (
        <div className="outcome-result">
          <p role="status" className="visually-hidden">
            Outcome map ready. {outcomeMap.diagnostics.combination_count.toLocaleString('en-US')}{' '}
            complete sets calculated; showing {outcomeMap.diagnostics.returned_outcome_count}.
          </p>
          <div className="outcome-result-heading">
            <div>
              <p className="eyebrow">Complete distribution</p>
              <h3>One coherent field of podium sets</h3>
            </div>
            <button type="button" onClick={clear}>
              Clear outcome map
            </button>
          </div>

          <div className="outcome-metrics" aria-label="Outcome map diagnostics">
            <div>
              <span>Complete sets</span>
              <b>{outcomeMap.diagnostics.combination_count.toLocaleString('en-US')}</b>
              <small>all included in the solution</small>
            </div>
            <div>
              <span>Effective outcomes</span>
              <b>{outcomeMap.diagnostics.effective_outcome_count.toFixed(1)}</b>
              <small>{outcomeMap.diagnostics.entropy_bits.toFixed(2)} bits of entropy</small>
            </div>
            <div>
              <span>Shown probability</span>
              <b>{percent(outcomeMap.diagnostics.returned_probability_sum)}</b>
              <small>cumulative mass of the ranked sets</small>
            </div>
            <div>
              <span>Reconstruction error</span>
              <b>{outcomeMap.diagnostics.maximum_marginal_error.toExponential(2)}</b>
              <small>maximum across all drivers</small>
            </div>
          </div>

          <div className="outcome-board">
            <div>
              <div className="outcome-subheading">
                <div>
                  <p className="eyebrow">Ranked combinations</p>
                  <h3>Most likely podium sets</h3>
                </div>
                <span>Order within each set is unspecified</span>
              </div>
              <ol className="outcome-ranking" aria-label="Most likely unordered podium sets">
                {outcomeMap.outcomes.map((outcome) => (
                  <li key={outcome.driver_ids.join('-')}>
                    <span className="outcome-rank">{String(outcome.rank).padStart(2, '0')}</span>
                    <div className="outcome-set">
                      <div>
                        {outcome.driver_ids.map((driverId) => (
                          <span key={driverId}>{driverName(driverId)}</span>
                        ))}
                      </div>
                      <span className="outcome-track" aria-hidden="true">
                        <span
                          style={{ width: `${(outcome.probability / topProbability) * 100}%` }}
                        />
                      </span>
                    </div>
                    <div className="outcome-probability">
                      <b>{percent(outcome.probability)}</b>
                      <small>Cumulative {percent(outcome.cumulative_probability)}</small>
                    </div>
                  </li>
                ))}
              </ol>
            </div>

            <aside className="outcome-pairs">
              <p className="eyebrow">Shared podium</p>
              <h3>Co-podium pairs</h3>
              <p>Probability that both drivers appear somewhere in the same three-driver set.</p>
              <ol aria-label="Most likely co-podium pairs">
                {outcomeMap.co_podium_pairs.map((pair) => (
                  <li key={pair.driver_ids.join('-')}>
                    <span>{pair.rank}</span>
                    <b>{pair.driver_ids.map(driverName).join(' + ')}</b>
                    <strong>{percent(pair.probability)}</strong>
                  </li>
                ))}
              </ol>
            </aside>
          </div>

          <div className="outcome-boundary">
            <div>
              <p className="eyebrow">Evidence boundary</p>
              <h3>Unordered three-driver sets</h3>
            </div>
            <p>{outcomeMap.evidence_boundary.statement}</p>
            <small>{outcomeMap.model_version}</small>
          </div>
        </div>
      )}
    </section>
  );
}

export default function PodiumOutcomeLab({ raceId, year }) {
  if (year < 2022)
    return (
      <section className="podium-outcome-lab outcome-state">
        <p className="eyebrow">Derived probability map</p>
        <h2>Podium outcome lab</h2>
        <p>Outcome maps begin with the 2022 evaluation window.</p>
      </section>
    );
  return <SupportedPodiumOutcomeLab raceId={raceId} />;
}
