import React, { useState } from 'react';
import { useApi } from './api';

const metrics = [
  ['constructor_name', 'Constructor'],
  ['grid', 'Recorded grid'],
  ['qualifying_position', 'Qualifying position'],
  ['recent_starts', 'Earlier appearances in form window'],
  ['recent_podiums', 'Podiums in form window'],
  ['recent_race_points', 'Race points in form window'],
  ['recent_average_classification', 'Average classification in form window'],
  ['circuit_starts', 'Earlier starts at this circuit'],
  ['circuit_podiums', 'Earlier podiums at this circuit'],
];
const format = (value) =>
  value == null
    ? 'Not recorded'
    : typeof value === 'number'
      ? value.toLocaleString(undefined, { maximumFractionDigits: 2 })
      : value;

function ComparisonResult({ raceId, left, right }) {
  const state = useApi(`/races/${raceId}/comparison?driver_a=${left}&driver_b=${right}`);
  if (state.loading) return <p role="status">Comparing earlier race history…</p>;
  if (state.error) return <p role="alert">{state.error}</p>;
  const { drivers, notes } = state.data;
  return (
    <>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">Before the race</th>
              {drivers.map((d) => (
                <th scope="col" key={d.driver_id}>
                  {d.driver_name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {metrics.map(([key, label]) => (
              <tr key={key}>
                <th scope="row">{label}</th>
                {drivers.map((d) => (
                  <td key={d.driver_id}>{format(d[key])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="caption">
        {notes[0]} {notes[1]} Grid zero denotes a pit-lane, unknown or nonstandard start.
      </p>
      <details>
        <summary>Compare with the recorded race outcome</summary>
        <p className="caption">{notes[2]}</p>
        {drivers.map((d) => (
          <p key={d.driver_id}>
            {d.driver_name}: finish {d.recorded_finish}, {format(d.recorded_points)} race points.
          </p>
        ))}
      </details>
    </>
  );
}

export default function DriverComparison({ raceId }) {
  const entrants = useApi(`/races/${raceId}/grid`);
  const [left, setLeft] = useState(''),
    [right, setRight] = useState('');
  if (entrants.loading) return <p role="status">Loading comparison drivers…</p>;
  if (entrants.error) return <p role="alert">{entrants.error}</p>;
  const rows = entrants.data.data;
  if (rows.length < 2) return <p>No pair of drivers is available for this race.</p>;
  const a = left || String(rows[0].driver_id);
  const b = right || String(rows[1].driver_id);
  return (
    <section className="comparison-panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Head to head</p>
          <h2>Driver comparison</h2>
        </div>
        <span>Earlier form and circuit record</span>
      </div>
      <div className="comparison-selectors">
        <label>
          First driver
          <select value={a} onChange={(e) => setLeft(e.target.value)}>
            {rows.map((d) => (
              <option key={d.driver_id} value={d.driver_id}>
                {d.driver_name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Second driver
          <select value={b} onChange={(e) => setRight(e.target.value)}>
            {rows.map((d) => (
              <option key={d.driver_id} value={d.driver_id}>
                {d.driver_name}
              </option>
            ))}
          </select>
        </label>
      </div>
      {a === b ? (
        <p role="status">Choose two different drivers to compare.</p>
      ) : (
        <ComparisonResult raceId={raceId} left={a} right={b} />
      )}
    </section>
  );
}
