import { describe, expect, it } from 'vitest';
import type { CaptureProgress } from '../application/useCaptures';
import { captureSteps } from './captureSteps';

const progress = (status: CaptureProgress['status'], log: string[], error: string | null = null) => ({
  status,
  log,
  error,
});

const states = (p: CaptureProgress) => captureSteps(p).map((step) => step.state);

describe('captureSteps', () => {
  it('shows no steps before a capture starts', () => {
    expect(captureSteps(progress('idle', []))).toEqual([]);
  });

  it('marks the first step current as soon as a capture starts, before any log line', () => {
    expect(states(progress('running', []))).toEqual(['current', 'waiting', 'waiting', 'waiting', 'waiting']);
  });

  it('follows the log: earlier steps are done and the reached one is current', () => {
    const log = [
      'Starting a headless browser',
      'Opening https://tvolearn.com/x',
      'Scrolling to load lazy images',
      'Saving 196 assets',
    ];

    expect(states(progress('running', log))).toEqual(['done', 'done', 'current', 'waiting', 'waiting']);
  });

  it('ignores log lines it does not know', () => {
    const log = ['Opening https://tvolearn.com/x', 'Something new the capture tool says'];

    expect(states(progress('running', log))).toEqual(['current', 'waiting', 'waiting', 'waiting', 'waiting']);
  });

  it('marks every step done when the capture is done', () => {
    expect(states(progress('done', ['Done: 288 elements']))).toEqual([
      'done',
      'done',
      'done',
      'done',
      'done',
    ]);
  });

  it('marks the step it stopped at as failed when the capture fails', () => {
    const log = ['Opening https://tvolearn.com/x', 'Scrolling to load lazy images'];

    expect(states(progress('error', log, 'Timed out'))).toEqual([
      'done',
      'failed',
      'waiting',
      'waiting',
      'waiting',
    ]);
  });
});
