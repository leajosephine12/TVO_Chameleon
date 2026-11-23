import { pageFromCapture, type PageCapture } from '../domain/capture';
import type { ReviewedPage } from '../domain/review';

interface Props {
  samplePage: ReviewedPage;
  page: ReviewedPage;
  /** Each captured link once, newest first (see useCaptures), so the options need no dates to tell them apart. */
  captures: PageCapture[];
  onPageChange: (page: ReviewedPage) => void;
}

const shortDate = (iso: string) =>
  new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });

/** Chooses the page under review: the example page or a captured one. Sits in the top bar. */
export function PagePicker({ samplePage, page, captures, onPageChange }: Props) {
  const capturedPages = captures.map((capture) => ({ capture, page: pageFromCapture(capture) }));
  const shownCapture = capturedPages.find((option) => option.page.url === page.url)?.capture;

  return (
    <label className="page-picker">
      <span className="page-picker-label">Page</span>
      <select
        value={page.url}
        onChange={(e) => {
          const next = [samplePage, ...capturedPages.map((option) => option.page)].find(
            (candidate) => candidate.url === e.target.value,
          );
          if (next) onPageChange(next);
        }}
      >
        <optgroup label="Example">
          <option value={samplePage.url}>{samplePage.label}</option>
        </optgroup>
        {capturedPages.length > 0 && (
          <optgroup label="Captured pages, newest first">
            {capturedPages.map(({ page: captured }) => (
              <option key={captured.url} value={captured.url}>
                {captured.label}
              </option>
            ))}
          </optgroup>
        )}
      </select>
      {shownCapture && (
        <span className="page-picker-date">Captured {shortDate(shownCapture.capturedAt)}</span>
      )}
    </label>
  );
}
