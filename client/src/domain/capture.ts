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

/** The page title without the site name TVO adds to every title, such as " | TVO Learn". */
const withoutSiteName = (title: string): string => title.replace(/\s*\|\s*TVO Learn$/, '');

export function pageFromCapture(capture: PageCapture): ReviewedPage {
  return { label: withoutSiteName(capture.title) || capture.sourceUrl, url: capture.pageUrl };
}

/**
 * The newest capture of each link, newest first. Capturing a link again replaces its earlier copy in
 * lists, so a page appears once however many times it was captured.
 */
export function latestCapturePerLink(captures: PageCapture[]): PageCapture[] {
  const newestFirst = [...captures].sort((a, b) => b.capturedAt.localeCompare(a.capturedAt));
  const seenLinks = new Set<string>();
  return newestFirst.filter((capture) => {
    const link = capture.sourceUrl.split('#')[0]; // a #section is the same page
    if (seenLinks.has(link)) return false;
    seenLinks.add(link);
    return true;
  });
}
