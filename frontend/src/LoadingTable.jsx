import React from 'react';

export default function LoadingTable({ label = 'Loading race data…', rows = 10 }) {
  return (
    <div className="table-loading">
      <p role="status" className="state table-loading-status">
        {label}
      </p>
      <div className="table-skeleton" aria-hidden="true">
        {Array.from({ length: rows }, (_, index) => (
          <span className="table-skeleton-row" key={index} />
        ))}
      </div>
    </div>
  );
}
