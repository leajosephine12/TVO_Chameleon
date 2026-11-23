import type { CaptureProgress } from '../application/useCaptures';

export type StepState = 'done' | 'current' | 'waiting' | 'failed';

export interface CaptureStep {
  label: string;
  state: StepState;
}

/**
 * The stages a capture goes through, in order, and the log lines that show each one has started.
 * The prefixes are the messages capture.js passes to `log(...)`; a line that matches none of them
 * leaves the steps as they are.
 */
const STAGES: Array<{ label: string; startsWith: string[] }> = [
  { label: 'Opening the page', startsWith: ['Starting a headless browser', 'Opening '] },
  {
    label: 'Loading the lesson and its tabs',
    startsWith: [
      'Scrolling to load',
      'Opened ',
      'Waiting for embedded content',
      'Taking a reference screenshot',
    ],
  },
  { label: 'Saving images and styles', startsWith: ['Fetching ', 'Saved ', 'Saving '] },
  { label: 'Saving the lesson', startsWith: ['Freezing the page', 'Copying embedded content', 'Left out '] },
  { label: 'Ready to review', startsWith: ['Done:'] },
];

/** The furthest stage the log has reached, or -1 before the first line arrives. */
function reachedStage(log: string[]): number {
  return log.reduce((furthest, line) => {
    const stage = STAGES.findIndex((s) => s.startsWith.some((prefix) => line.startsWith(prefix)));
    return Math.max(furthest, stage);
  }, -1);
}

/**
 * Turns a capture's log into a short list of steps a reviewer can follow, instead of the raw log.
 * Every step before the one reached is done; the reached one is current, or failed if the capture failed.
 */
export function captureSteps(progress: CaptureProgress): CaptureStep[] {
  if (progress.status === 'idle') return [];
  const lastStage = STAGES.length - 1;
  const reached = progress.status === 'done' ? lastStage : Math.max(reachedStage(progress.log), 0);

  return STAGES.map(({ label }, index) => {
    let state: StepState = 'waiting';
    if (index < reached || (index === lastStage && progress.status === 'done')) state = 'done';
    else if (index === reached) state = progress.status === 'error' ? 'failed' : 'current';
    return { label, state };
  });
}
