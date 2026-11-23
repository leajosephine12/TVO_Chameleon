import { useEffect, useRef, useState, type FormEvent } from 'react';
import type { CaptureProgress } from '../application/useCaptures';
import { captureSteps, type StepState } from './captureSteps';

const STEP_ICON_LABEL: Record<StepState, string> = {
  done: 'Done',
  current: 'In progress',
  waiting: 'Not started',
  failed: 'Failed',
};

/** The capture's progress as a few plain steps. The full log stays one click away for when something breaks. */
function CaptureProgressView({ progress }: { progress: CaptureProgress }) {
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
}

/**
 * The "Capture a page" button in the top bar and the pop-up it opens, where a TVO Learn link is pasted and
 * the capture's progress is shown. The pop-up can be closed while a capture runs and opened again to check it.
 */
export function CaptureMenu({ serverReachable, progress, onCapture }: Props) {
  const [isOpen, setIsOpen] = useState(false);
  const [url, setUrl] = useState('');
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
    onCapture(url.trim());
  };

  return (
    <div className="capture-menu" ref={menuRef}>
      <button
        type="button"
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
          <CaptureProgressView progress={progress} />
        </section>
      )}
    </div>
  );
}
