import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { AnalysisGateway, ReviewRepository } from '../application/ports';
import type { Recommendation } from '../domain/analysis';
import type { ReviewedPage } from '../domain/review';
import {
  ANALYSIS_UNAVAILABLE_NOTE,
  createAnalysisReviewRepository,
  MODEL_UNAVAILABLE_NOTE,
} from './analysisReviewRepository';

const LESSON = `<body>
  <a href="#mindsOn" data-tab-trigger="mindsOn" data-tab-order="0">Minds On</a>
  <a href="#action" data-tab-trigger="action" data-tab-order="1">Action</a>
  <a href="#consolidation" data-tab-trigger="consolidation" data-tab-order="2">Consolidation</a>
  <section id="mindsOn" data-tab-panel="0"><p data-cid="a">Intro</p></section>
  <section id="action" data-tab-panel="0"><p data-cid="b"><i data-cid="c">Key</i></p></section>
  <section id="consolidation" data-tab-panel="0"><p data-cid="d">Wrap up</p></section>
</body>`;

/** A lesson whose tabs are not the usual three. */
const OTHER_TABS_LESSON = `<body>
  <a href="#one" data-tab-trigger="one" data-tab-order="0">Reading</a>
  <a href="#two" data-tab-trigger="two" data-tab-order="1">Quiz</a>
  <section id="one" data-tab-panel="0"><p data-cid="a">Text</p></section>
  <section id="two" data-tab-panel="0"><p data-cid="b"><i data-cid="c">Key</i></p></section>
</body>`;

const ITALIC_IN_ACTION_TAB: Recommendation = {
  id: 'r1',
  block_id: 'i-1',
  type: 'italic_text',
  original: '<i>Key</i>',
  suggestion: '<strong>Key</strong>',
  rationale: 'Italics are hard to read.',
  evidence: 'Level 1 guideline',
  severity: 'low',
  status: 'pending',
};

const samplePage: ReviewedPage = { label: 'Sample', url: '/sample.html' };
const capturedPage: ReviewedPage = { label: 'Captured', url: '/snapshots/x/frames/f0.html' };

const fallback: ReviewRepository = {
  loadSession: async () => ({
    targetFrame: null,
    lessonTabs: [],
    versions: [
      { id: 'general', name: 'General', shortName: 'general', note: '', suggestions: [] },
      { id: 'dyslexia', name: 'Dyslexia', shortName: 'dyslexia', note: '', suggestions: [] },
    ],
    decisions: {},
  }),
  saveDecision: async () => undefined,
};

function backendReturning(...results: Array<Recommendation[] | Error>) {
  const analyze = vi.fn<AnalysisGateway['analyze']>(async () => {
    const next = results.shift() ?? [];
    if (next instanceof Error) throw next;
    return { recommendations: next, modelError: null };
  });
  const gateway: AnalysisGateway = {
    analyze,
    adapt: async () => ({ injectedCss: '', applied: [], skipped: [] }),
  };
  return { analyze, gateway };
}

// The repository logs the technical reason for a missing analysis; keep that out of the test output.
beforeEach(() => {
  vi.spyOn(console, 'warn').mockImplementation(() => undefined);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function serveLesson(html = LESSON) {
  vi.stubGlobal('fetch', async () => new Response(html));
}

describe('createAnalysisReviewRepository', () => {
  it('gives the lesson tabs and puts each suggestion under the tab it is in', async () => {
    serveLesson();
    const { gateway } = backendReturning([ITALIC_IN_ACTION_TAB]);

    const session = await createAnalysisReviewRepository(fallback, gateway, samplePage).loadSession(
      capturedPage,
    );

    expect(session.lessonTabs.map((tab) => tab.id)).toEqual(['mindsOn', 'action', 'consolidation']);
    const dyslexia = session.versions.find((v) => v.id === 'dyslexia');
    expect(dyslexia?.suggestions.map((s) => s.tabId)).toEqual(['action']);
  });

  it('keeps one list when the lesson does not have the usual three tabs', async () => {
    serveLesson(OTHER_TABS_LESSON);
    const { gateway } = backendReturning([ITALIC_IN_ACTION_TAB]);

    const session = await createAnalysisReviewRepository(fallback, gateway, samplePage).loadSession(
      capturedPage,
    );

    expect(session.lessonTabs).toEqual([]);
    expect(session.versions.find((v) => v.id === 'dyslexia')?.suggestions.map((s) => s.tabId)).toEqual([
      null,
    ]);
  });

  it('analyses a page once, however many times it is opened', async () => {
    serveLesson();
    const { analyze, gateway } = backendReturning([ITALIC_IN_ACTION_TAB]);
    const repository = createAnalysisReviewRepository(fallback, gateway, samplePage);

    await repository.loadSession(capturedPage);
    const again = await repository.loadSession(capturedPage);

    expect(analyze).toHaveBeenCalledTimes(1);
    expect(again.versions.find((v) => v.id === 'dyslexia')?.suggestions).toHaveLength(1);
  });

  it('tries again when the first analysis failed, for example because the backend was down', async () => {
    serveLesson();
    const { analyze, gateway } = backendReturning(new Error('down'), [ITALIC_IN_ACTION_TAB]);
    const repository = createAnalysisReviewRepository(fallback, gateway, samplePage);

    const failed = await repository.loadSession(capturedPage);
    const retried = await repository.loadSession(capturedPage);

    expect(failed.versions.find((v) => v.id === 'dyslexia')?.suggestions).toHaveLength(0);
    expect(retried.versions.find((v) => v.id === 'dyslexia')?.suggestions).toHaveLength(1);
    expect(analyze).toHaveBeenCalledTimes(2);
  });

  it('tells the reviewer in plain words when the language model was not reached, and keeps the details in the console', async () => {
    serveLesson();
    const gateway: AnalysisGateway = {
      analyze: async () => ({ recommendations: [ITALIC_IN_ACTION_TAB], modelError: 'MODEL_NAME is not set' }),
      adapt: async () => ({ injectedCss: '', applied: [], skipped: [] }),
    };

    const session = await createAnalysisReviewRepository(fallback, gateway, samplePage).loadSession(
      capturedPage,
    );

    const note = session.versions.find((v) => v.id === 'dyslexia')?.note ?? '';
    expect(note).toContain(MODEL_UNAVAILABLE_NOTE);
    expect(note).not.toContain('MODEL_NAME');
    expect(console.warn).toHaveBeenCalledWith(expect.stringContaining('MODEL_NAME is not set'));
  });

  it('says on every version that the suggestions could not be loaded, without the technical reason', async () => {
    serveLesson();
    const { gateway } = backendReturning(new Error('connect ECONNREFUSED 127.0.0.1:8001'));

    const session = await createAnalysisReviewRepository(fallback, gateway, samplePage).loadSession(
      capturedPage,
    );

    for (const version of session.versions) {
      expect(version.note).toContain(ANALYSIS_UNAVAILABLE_NOTE);
      expect(version.note).not.toContain('ECONNREFUSED');
    }
  });
});
