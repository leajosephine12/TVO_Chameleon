import { describe, expect, it } from 'vitest';
import { latestCapturePerLink, pageFromCapture, type PageCapture } from './capture';

function capture(overrides: Partial<PageCapture>): PageCapture {
  return {
    id: 'a',
    sourceUrl: 'https://tvolearn.com/products/budget',
    title: 'Budget | TVO Learn',
    capturedAt: '2026-11-06T10:00:00Z',
    pageUrl: '/snapshots/a/index.html',
    ...overrides,
  };
}

describe('latestCapturePerLink', () => {
  it('keeps only the newest of several captures of the same link', () => {
    const captures = [
      capture({ id: 'first', capturedAt: '2026-11-06T10:00:00Z' }),
      capture({ id: 'third', capturedAt: '2026-11-06T10:06:00Z' }),
      capture({ id: 'second', capturedAt: '2026-11-06T10:03:00Z' }),
    ];

    expect(latestCapturePerLink(captures).map((c) => c.id)).toEqual(['third']);
  });

  it('keeps one capture of each different link, newest first', () => {
    const captures = [
      capture({ id: 'budget', capturedAt: '2026-11-06T10:00:00Z' }),
      capture({
        id: 'history',
        sourceUrl: 'https://tvolearn.com/products/history',
        capturedAt: '2026-11-06T11:00:00Z',
      }),
    ];

    expect(latestCapturePerLink(captures).map((c) => c.id)).toEqual(['history', 'budget']);
  });

  it('treats a link with a #section as the same page', () => {
    const captures = [
      capture({ id: 'plain', capturedAt: '2026-11-06T10:00:00Z' }),
      capture({
        id: 'section',
        sourceUrl: 'https://tvolearn.com/products/budget#tips',
        capturedAt: '2026-11-06T10:05:00Z',
      }),
    ];

    expect(latestCapturePerLink(captures).map((c) => c.id)).toEqual(['section']);
  });

  it('does not change the list it is given', () => {
    const captures = [capture({ id: 'old' }), capture({ id: 'new', capturedAt: '2026-11-06T12:00:00Z' })];

    latestCapturePerLink(captures);

    expect(captures.map((c) => c.id)).toEqual(['old', 'new']);
  });
});

describe('pageFromCapture', () => {
  it('drops the site name TVO adds to the title', () => {
    expect(pageFromCapture(capture({})).label).toBe('Budget');
  });

  it('falls back to the link when the page has no title', () => {
    expect(pageFromCapture(capture({ title: '' })).label).toBe('https://tvolearn.com/products/budget');
  });
});
