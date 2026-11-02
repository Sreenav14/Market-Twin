import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { CountBars } from './ReportIntelligence';

afterEach(cleanup);

it('scales recorded counts against the full denominator and keeps zero empty', async () => {
  const select = vi.fn();
  render(<CountBars title="Outcomes" rows={[
    { key: 'passed', label: 'Passed', count: 2 },
    { key: 'failed', label: 'Failed', count: 1 },
    { key: 'blocked', label: 'Blocked', count: 0 },
  ]} denominator={6} onSelect={select} />);
  expect(screen.getByText(/axis 0–6/)).toBeInTheDocument();
  const passed = screen.getByRole('button', { name: 'Passed 2' });
  expect(passed.querySelector('.count-bar-track > span')).toHaveStyle({ width: `${2 / 6 * 100}%` });
  expect(screen.getByRole('button', { name: 'Blocked 0' }).querySelector('.count-bar-track > span')).toHaveStyle({ width: '0%' });
  await userEvent.click(passed);
  expect(select).toHaveBeenCalledWith('passed');
});

it('uses the record total by default and handles a zero denominator honestly', () => {
  const { rerender } = render(<CountBars title="Counts" rows={[
    { key: 'one', label: 'One', count: 2 }, { key: 'two', label: 'Two', count: 1 },
  ]} onSelect={() => {}} />);
  expect(screen.getByText(/axis 0–3/)).toBeInTheDocument();
  rerender(<CountBars title="Counts" rows={[{ key: 'none', label: 'None', count: 0 }]} onSelect={() => {}} />);
  expect(screen.getByText(/axis 0–0/)).toBeInTheDocument();
  expect(screen.getByRole('button').querySelector('.count-bar-track > span')).toHaveStyle({ width: '0%' });
});
