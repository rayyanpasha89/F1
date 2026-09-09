import React from 'react';

export function chartRows(result) {
  if (!result || result.columns.length !== 2 || result.rows.length < 2 || result.rows.length > 20)
    return null;
  if (/\b(id|year|latitude|longitude)\b/i.test(result.columns[1].replaceAll('_', ' '))) return null;
  if (
    !result.rows.every(
      (row) =>
        typeof row[0] === 'string' &&
        typeof row[1] === 'number' &&
        Number.isFinite(row[1]) &&
        row[1] >= 0,
    )
  )
    return null;
  if (new Set(result.rows.map((row) => row[0])).size !== result.rows.length) return null;
  return result.rows;
}

export default function QueryChart({ result }) {
  const rows = chartRows(result);
  if (!rows) return null;
  const max = Math.max(1, ...rows.map((row) => row[1]));
  return (
    <details className="query-chart">
      <summary>Visualize {result.columns[1].replaceAll('_', ' ')}</summary>
      <figure aria-label={`${result.columns[1]} by ${result.columns[0]}`}>
        {rows.map(([label, value]) => (
          <div className="query-bar" key={label}>
            <span>{label}</span>
            <span className="query-bar-track" aria-hidden="true">
              <span style={{ width: `${(100 * value) / max}%` }} />
            </span>
            <b>{value.toLocaleString(undefined, { maximumFractionDigits: 3 })}</b>
          </div>
        ))}
        <figcaption className="caption">
          Same executed rows as the table. Scale starts at zero.
        </figcaption>
      </figure>
    </details>
  );
}
