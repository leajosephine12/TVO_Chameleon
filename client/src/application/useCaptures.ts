import { useCallback, useEffect, useState } from 'react';
import type { PageCapture } from '../domain/capture';
import type { CaptureGateway } from './ports';

export interface CaptureProgress {
  status: 'idle' | 'running' | 'done' | 'error';
  log: string[];
  error: string | null;
}

const POLL_MS = 800;
const IDLE: CaptureProgress = { status: 'idle', log: [], error: null };

/** Lists earlier captures and runs new ones. `onCaptured` must be stable, as with useCallback. */
export function useCaptures(gateway: CaptureGateway, onCaptured: (capture: PageCapture) => void) {
  const [captures, setCaptures] = useState<PageCapture[]>([]);
  const [serverReachable, setServerReachable] = useState(true);
  const [progress, setProgress] = useState<CaptureProgress>(IDLE);
  const [jobId, setJobId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    gateway
      .listCaptures()
      .then((list) => {
        if (cancelled) return;
        setCaptures(list);
        setServerReachable(true);
      })
      .catch(() => {
        if (!cancelled) setServerReachable(false);
      });
    return () => {
      cancelled = true;
    };
  }, [gateway]);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = () =>
      gateway
        .getJob(jobId)
        .then((job) => {
          if (cancelled) return;
          setProgress({ status: job.status, log: job.log, error: job.error });
          if (job.status === 'running') {
            timer = setTimeout(poll, POLL_MS);
            return;
          }
          setJobId(null);
          const { capture } = job;
          if (capture) {
            setCaptures((list) => [capture, ...list.filter((c) => c.id !== capture.id)]);
            onCaptured(capture);
          }
        })
        .catch(() => {
          if (cancelled) return;
          setJobId(null);
          setProgress((p) => ({ ...p, status: 'error', error: 'Lost contact with the capture server.' }));
        });
    void poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [gateway, jobId, onCaptured]);

  const startCapture = useCallback(
    (url: string) => {
      setProgress({ status: 'running', log: [], error: null });
      gateway
        .startCapture(url)
        .then((id) => {
          setServerReachable(true);
          setJobId(id);
        })
        .catch((e: Error) => setProgress({ status: 'error', log: [], error: e.message }));
    },
    [gateway],
  );

  return { captures, serverReachable, progress, startCapture };
}
