import { useEffect, useRef, useState, type FormEvent } from 'react';
import type { CaptureProgress } from '../application/useCaptures';

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
  serverReachable: boolean;
  progress: CaptureProgress;
  onCapture: (url: string) => void;
}

/**
 * The "Capture a page" button in the top bar and the pop-up it opens, where a TVO Learn link is pasted and
 * the capture's progress is shown. The pop-up can be closed while a capture runs and opened again to check it.
 */
export function CaptureMenu({ serverReachable, progress, onCapture }: Props) {
  const [isOpen, setIsOpen] = useState(false);
  const [url, setUrl] = useState('');
  const [logExpanded, setLogExpanded] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const running = progress.status === 'running';

  // Like any pop-up, it closes on Escape or on a click anywhere outside it.
  useEffect(() => {
    if (!isOpen) return undefined;
    const closeOnOutsideClick = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) setIsOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setIsOpen(false);
    };
    document.addEventListener('mousedown', closeOnOutsideClick);
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('mousedown', closeOnOutsideClick);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, [isOpen]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setLogExpanded(false);
    onCapture(url.trim());
  };

  return (
    <div className="capture-menu" ref={menuRef}>
      <button
        type="button"
        className="capture-button"
        aria-expanded={isOpen}
        aria-controls="capture-popover"
        onClick={() => setIsOpen((open) => !open)}
      >
        <svg
          aria-hidden="true"
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.2"
          strokeLinecap="round"
        >
          <path d="M12 5v14M5 12h14" />
        </svg>
        {running ? 'Capturing…' : 'Capture a page'}
      </button>
      {isOpen && (
        <section id="capture-popover" className="capture-popover" aria-label="Capture a page">
          <form className="capture-form" onSubmit={submit}>
            <label className="field">
              TVO Learn link
              <input
                type="url"
                required
                placeholder="https://tvolearn.com/..."
                autoComplete="off"
                autoFocus
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
            </label>
            <button type="submit" className="capture-button" disabled={running || !serverReachable}>
              Capture
            </button>
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
      )}
    </div>
  );
}
