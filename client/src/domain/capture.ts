import type { ReviewedPage } from './review';

/** A static copy of a TVO Learn page, made by the capture tool. */
export interface PageCapture {
  id: string;
  sourceUrl: string;
  title: string;
  capturedAt: string;
  pageUrl: string;
}

export interface CaptureJob {
  status: 'running' | 'done' | 'error';
  log: string[];
  capture: PageCapture | null;
  error: string | null;
}

export function pageFromCapture(capture: PageCapture): ReviewedPage {
  return { label: capture.title || capture.sourceUrl, url: capture.pageUrl };
}
