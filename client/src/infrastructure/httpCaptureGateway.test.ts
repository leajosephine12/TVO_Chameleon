import { afterEach, describe, expect, it, vi } from 'vitest';
import { createHttpCaptureGateway } from './httpCaptureGateway';

/** Makes the capture server answer with the given snapshots. */
function serveSnapshots(snapshots: unknown[]): void {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(snapshots))));
}

const meta = {
  id: 'abc',
  sourceUrl: 'https://tvolearn.com/x',
  title: 'X',
  capturedAt: '2026-11-01T00:00:00Z',
};

afterEach(() => vi.unstubAllGlobals());

describe('listCaptures', () => {
  it('shows the lesson alone for a learning activity', async () => {
    serveSnapshots([{ ...meta, lessonFrame: 'frames/f0.html' }]);

    const [capture] = await createHttpCaptureGateway().listCaptures();

    expect(capture.pageUrl).toBe('/snapshots/abc/frames/f0.html');
  });

  it('shows the whole page when there is no single lesson, as on a course page', async () => {
    serveSnapshots([{ ...meta, lessonFrame: null }]);

    const [capture] = await createHttpCaptureGateway().listCaptures();

    expect(capture.pageUrl).toBe('/snapshots/abc/index.html');
  });
});
