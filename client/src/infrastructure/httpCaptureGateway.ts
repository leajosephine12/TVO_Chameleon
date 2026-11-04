import type { CaptureGateway } from '../application/ports';
import type { PageCapture } from '../domain/capture';
import { requestJson } from './requestJson';

/** The parts of the capture server's meta.json that the client uses. */
interface CaptureMeta {
  id: string;
  sourceUrl: string;
  title: string;
  capturedAt: string;
}

function toCapture(meta: CaptureMeta): PageCapture {
  return {
    id: meta.id,
    sourceUrl: meta.sourceUrl,
    title: meta.title,
    capturedAt: meta.capturedAt,
    pageUrl: `/snapshots/${meta.id}/index.html`,
  };
}

/** Talks to the capture server (server.js on the PullingTVOWebsitesDraftVersion branch). */
export function createHttpCaptureGateway(): CaptureGateway {
  return {
    listCaptures: async () => (await requestJson<CaptureMeta[]>('/api/snapshots')).map(toCapture),
    startCapture: async (url) => {
      const { jobId } = await requestJson<{ jobId: string }>('/api/capture', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url }),
      });
      return jobId;
    },
    getJob: async (jobId) => {
      const job = await requestJson<{
        status: 'running' | 'done' | 'error';
        log: string[];
        snapshot: CaptureMeta | null;
        error: string | null;
      }>(`/api/jobs/${encodeURIComponent(jobId)}`);
      return {
        status: job.status,
        log: job.log,
        error: job.error,
        capture: job.snapshot && toCapture(job.snapshot),
      };
    },
  };
}
