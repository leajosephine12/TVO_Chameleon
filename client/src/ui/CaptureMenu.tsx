import { useEffect, useRef, useState, type FormEvent } from 'react';
import type { CaptureProgress } from '../application/useCaptures';
import type { ReviewedPage } from '../domain/review';
import { captureSteps, type StepState } from './captureSteps';

const STEP_ICON_LABEL: Record<StepState, string> = {
  done: 'Done',
  current: 'In progress',
  waiting: 'Not started',
  failed: 'Failed',
};

/** The capture's progress as a few plain steps. The full log stays one click away for when something breaks. */
function CaptureProgressView({
  progress,
  capturedPageToOpen,
  onPageChange,
}: {
  progress: CaptureProgress;
  capturedPageToOpen: ReviewedPage | null;
  onPageChange: (page: ReviewedPage) => void;
}) {
  const [showLog, setShowLog] = useState(false);
  const steps = captureSteps(progress);
  if (steps.length === 0) return null;

  return (
    <div className="capture-progress">
      <ol className="capture-steps" role="status">
        {steps.map((step) => (
          <li key={step.label} className={`capture-step step-${step.state}`}>
            <span className="step-icon" role="img" aria-label={STEP_ICON_LABEL[step.state]} />
            {step.label}
          </li>
        ))}
      </ol>
      {progress.error && <p className="error">{progress.error}</p>}
      {/* The reviewer moved to another page while this one was capturing, so it waits here instead of opening. */}
      {progress.status === 'done' && capturedPageToOpen && (
        <button type="button" className="log-toggle" onClick={() => onPageChange(capturedPageToOpen)}>
          Open {capturedPageToOpen.label}
        </button>
      )}
      {progress.status === 'running' && (
        <p className="capture-note">This takes a few minutes. You can close this and keep reviewing.</p>
      )}
      {progress.log.length > 0 && (
        <>
          <button
            type="button"
            className="log-toggle"
            aria-expanded={showLog}
            aria-controls="capture-log"
            onClick={() => setShowLog((shown) => !shown)}
          >
            {showLog ? 'Hide log' : 'Show log'}
          </button>
          {showLog && (
            <ul id="capture-log" className="capture-log">
              {progress.log.map((line, index) => (
                <li key={index}>{line}</li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}

interface Props {
  serverReachable: boolean;
  progress: CaptureProgress;
  onCapture: (url: string) => void;
  onPageChange: (page: ReviewedPage) => void;
  /** A page that finished capturing after the reviewer moved on, offered here instead of opened. */
  capturedPageToOpen: ReviewedPage | null;
}

/**
 * The "Capture a page" button in the top bar and the pop-up it opens, where a TVO Learn link is pasted and
 * the capture's progress is shown. The pop-up can be closed while a capture runs and opened again to check it.
 */
export function CaptureMenu({
  serverReachable,
  progress,
  onCapture,
  onPageChange,
  capturedPageToOpen,
}: Props) {
  const [isOpen, setIsOpen] = useState(false);
  const [url, setUrl] = useState('');
  const menuRef = useRef<HTMLDivElement>(null);
  const openButtonRef = useRef<HTMLButtonElement>(null);
  const running = progress.status === 'running';

  // Like any pop-up, it closes on Escape or on a click anywhere outside it. Escape puts focus back on the
  // button that opened it, so a keyboard user is not left on a field that has just disappeared.
  useEffect(() => {
    if (!isOpen) return undefined;
    const closeOnOutsideClick = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) setIsOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      setIsOpen(false);
      openButtonRef.current?.focus();
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
    onCapture(url.trim());
  };

  return (
    <div className="capture-menu" ref={menuRef}>
      <button
        type="button"
        ref={openButtonRef}
        className="capture-open-button"
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
        {/* On phones only the + shows; the words stay for screen readers. */}
        <span className="label-wide-only">{running ? 'Capturing…' : 'Capture a page'}</span>
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
          <CaptureProgressView
            progress={progress}
            capturedPageToOpen={capturedPageToOpen}
            onPageChange={onPageChange}
          />
        </section>
      )}
    </div>
  );
}
