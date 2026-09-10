import React from 'react';
import { Link } from 'react-router-dom';
import { useApi } from './api';

const percent = (value) => `${(value * 100).toFixed(1)}%`;

function PodiumLane({ label, rows, recorded = false }) {
  return (
    <div className={`review-lane ${recorded ? 'review-lane--recorded' : ''}`}>
      <h3>{label}</h3>
      <ol aria-label={label}>
        {rows.map((row) => (
          <li key={row.driver_id}>
            <span className="review-position">P{row.rank}</span>
            <span>
              <b>{row.driver_name}</b>
              <small>{row.constructor_name}</small>
            </span>
            <strong>{recorded ? 'Finished' : percent(row.probability)}</strong>
          </li>
        ))}
      </ol>
    </div>
  );
}

function SupportedForecastReview({ raceId }) {
  const state = useApi(`/predictions/${raceId}/review`);
  if (state.loading)
    return (
      <section className="forecast-review review-state" aria-labelledby="review-loading-title">
        <p className="eyebrow">Race lab</p>
        <h2 id="review-loading-title">Preparing race review</h2>
        <p role="status">Building the post-race review…</p>
      </section>
    );
  if (state.error)
    return (
      <section className="forecast-review review-state" aria-labelledby="review-error-title">
        <p className="eyebrow">Race lab</p>
        <h2 id="review-error-title">Forecast vs reality</h2>
        <p role="alert">{state.error}</p>
      </section>
    );
  const review = state.data;
  return (
    <section className="forecast-review" aria-labelledby="forecast-review-title">
      <div className="review-heading">
        <div>
          <p className="eyebrow">Post-race review</p>
          <h2 id="forecast-review-title">Forecast vs reality</h2>
        </div>
        <span className="review-version">{review.model_version}</span>
      </div>
      <p className="review-intro">
        The forecast was built from the grid and earlier history. Recorded finishes enter only here,
        after prediction, as evaluation labels.
      </p>
      <div className="review-board">
        <PodiumLane label="Predicted podium" rows={review.predicted_podium} />
        <div
          className="review-score"
          aria-label={`${review.top_three_hits} of 3 podium drivers matched`}
        >
          <span>Podium hits</span>
          <b>{review.top_three_hits} / 3</b>
          <strong>{review.exact_podium_set ? 'Exact podium set' : 'Partial podium set'}</strong>
        </div>
        <PodiumLane label="Recorded podium" rows={review.recorded_podium} recorded />
      </div>
      <div className="review-metrics">
        <div>
          <span>Brier score</span>
          <b>{review.brier_score.toFixed(4)}</b>
          <small>Lower is better</small>
        </div>
        <div>
          <span>Mean absolute error</span>
          <b>{review.mean_absolute_error.toFixed(4)}</b>
          <small>Across every entrant</small>
        </div>
        <p>
          Brier score averages squared probability error across the full grid. A confident miss
          costs more than a cautious miss.
        </p>
      </div>
      <div className="surprise-strip">
        <div>
          <span>Largest overprediction</span>
          <b>{review.surprises.largest_overprediction.driver_name}</b>
          <small>
            {percent(review.surprises.largest_overprediction.probability)} forecast · +
            {review.surprises.largest_overprediction.error.toFixed(3)} error
          </small>
        </div>
        <div>
          <span>Largest underprediction</span>
          <b>{review.surprises.largest_underprediction.driver_name}</b>
          <small>
            {percent(review.surprises.largest_underprediction.probability)} forecast · +
            {review.surprises.largest_underprediction.error.toFixed(3)} error
          </small>
        </div>
      </div>
      <div className="review-ledger table-scroll">
        <table aria-label="Forecast review by driver">
          <thead>
            <tr>
              <th scope="col">Forecast rank</th>
              <th scope="col">Driver</th>
              <th scope="col">Grid</th>
              <th scope="col">Probability</th>
              <th scope="col">Finish</th>
              <th scope="col">Absolute error</th>
            </tr>
          </thead>
          <tbody>
            {review.drivers.map((row) => (
              <tr key={row.driver_id}>
                <td>{row.predicted_rank}</td>
                <td>
                  <Link to={`/drivers/${row.driver_id}?year=${review.race.year}`}>
                    {row.driver_name}
                  </Link>
                  <small>{row.constructor_name}</small>
                </td>
                <td>{row.grid || 'Pit lane'}</td>
                <td>{percent(row.probability)}</td>
                <td>{row.recorded_finish}</td>
                <td>{row.absolute_error.toFixed(3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="review-footer">
        <p>{review.notes[1] || review.notes[0]}</p>
        <Link to="/model">Open model accountability →</Link>
      </div>
    </section>
  );
}

export default function ForecastReview({ raceId, year }) {
  if (year < 2022)
    return (
      <section className="forecast-review review-state">
        <p className="eyebrow">Race lab</p>
        <h2>Forecast vs reality</h2>
        <p>Forecast reviews begin with the 2022 evaluation window.</p>
      </section>
    );
  return <SupportedForecastReview raceId={raceId} />;
}
