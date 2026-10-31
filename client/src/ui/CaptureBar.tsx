import { useState, type FormEvent } from 'react';
import type { CaptureProgress } from '../application/useCaptures';
import { pageFromCapture, type PageCapture } from '../domain/capture';
import type { ReviewedPage } from '../domain/review';

const LOG_LINES = 2;

const STATUS_TEXT: Partial<Record<CaptureProgress['status'], string>> = {
  running: 'Capturing…',
  done: 'Captured.',
};

interface LogProps {
  lines: string[];
  expanded: boolean;
  onToggle: () => void;
}

/** Collapsed, the log shows only its newest lines, so progress stays visible. */
function CaptureLog({ lines, expanded, onToggle }: LogProps) {
  const canCollapse = lines.length > LOG_LINES;
  const collapsed = canCollapse && !expanded;
  return (
    <>
      <ul id="capture-log" className={collapsed ? 'capture-log collapsed' : 'capture-log'}>
        {(collapsed ? lines.slice(-LOG_LINES) : lines).map((line, index) => (
          <li key={index}>{line}</li>
        ))}
      </ul>
      {canCollapse && (
        <button
          type="button"
          className="log-toggle"
          aria-expanded={expanded}
          aria-controls="capture-log"
          onClick={onToggle}
        >
          {expanded ? 'Show less' : 'Show more'}
        </button>
      )}
    </>
  );
}

interface Props {
  samplePage: ReviewedPage;
  page: ReviewedPage;
  captures: PageCapture[];
  serverReachable: boolean;
  progress: CaptureProgress;
  onCapture: (url: string) => void;
  onPageChange: (page: ReviewedPage) => void;
}

export function CaptureBar({
  samplePage,
  page,
  captures,
  serverReachable,
  progress,
  onCapture,
  onPageChange,
}: Props) {
  const [url, setUrl] = useState('');
  const [logExpanded, setLogExpanded] = useState(false);
  const running = progress.status === 'running';
  // The same link can be captured more than once, so captures also show when they were made.
  const options = [
    { page: samplePage, text: samplePage.label },
    ...captures.map((capture) => {
      const captured = pageFromCapture(capture);
      return { page: captured, text: `${captured.label} (${new Date(capture.capturedAt).toLocaleString()})` };
    }),
  ];

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setLogExpanded(false);
    onCapture(url.trim());
  };

  return (
    <section className="capture-bar" aria-label="Page capture">
      <form className="capture-form" onSubmit={submit}>
        <label className="field field-url">
          TVO Learn link
          <input
            type="url"
            required
            placeholder="https://tvolearn.com/..."
            autoComplete="off"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
        </label>
        <button type="submit" className="capture-button" disabled={running}>
          Capture page
        </button>
        <label className="field field-page">
          Page to review
          <select
            value={page.url}
            onChange={(e) => {
              const next = options.find((o) => o.page.url === e.target.value);
              if (next) onPageChange(next.page);
            }}
          >
            {options.map((o) => (
              <option key={o.page.url} value={o.page.url}>
                {o.text}
              </option>
            ))}
          </select>
        </label>
      </form>
      {!serverReachable && (
        <p className="capture-note">
          The capture server is not running, so only the sample page is available.
        </p>
      )}
      <div role="status">
        {progress.error && <p className="error">{progress.error}</p>}
        {STATUS_TEXT[progress.status] && <p className="capture-status">{STATUS_TEXT[progress.status]}</p>}
      </div>
      <CaptureLog
        lines={progress.log}
        expanded={logExpanded}
        onToggle={() => setLogExpanded((expanded) => !expanded)}
      />
    </section>
  );
}
