import { describe, it, expect } from 'vitest';
import { chartRows } from './QueryChart';

describe('query chart eligibility', () => {
  it('preserves executed values and labels without aggregation', () => {
    const result = {
      columns: ['driver', 'wins'],
      rows: [
        ['A', 3],
        ['B', 0],
      ],
    };
    expect(chartRows(result)).toBe(result.rows);
  });
  it('rejects ambiguous, identifier and incompatible outputs', () => {
    for (const result of [
      {
        columns: ['driver', 'driver_id'],
        rows: [
          ['A', 1],
          ['B', 2],
        ],
      },
      {
        columns: ['driver', 'wins'],
        rows: [
          ['A', 1],
          ['A', 2],
        ],
      },
      {
        columns: ['driver', 'wins'],
        rows: [
          ['A', null],
          ['B', 2],
        ],
      },
      {
        columns: ['driver', 'wins'],
        rows: [
          ['A', -1],
          ['B', 2],
        ],
      },
      { columns: ['wins'], rows: [[2], [3]] },
    ])
      expect(chartRows(result)).toBeNull();
  });
});
