import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import LoadingTable from './LoadingTable';

afterEach(cleanup);

it('reserves table geometry while keeping loading status visible', () => {
  const { container } = render(<LoadingTable label="Loading driver standings…" rows={10} />);

  expect(screen.getByRole('status')).toHaveTextContent('Loading driver standings');
  expect(container.querySelector('.table-skeleton')).toHaveAttribute('aria-hidden', 'true');
  expect(container.querySelectorAll('.table-skeleton-row')).toHaveLength(10);
});
