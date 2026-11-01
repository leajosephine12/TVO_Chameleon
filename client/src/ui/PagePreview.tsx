import { useEffect, useRef, useState, type ReactNode } from 'react';
import type { Patch } from '../domain/review';
import { applyPatches } from './applyPatches';
import { fitEmbeddedFrames } from './fitEmbeddedFrames';

interface Props {
  url: string;
  addressLabel: string;
  patches: Patch[];
  highlightSelector: string | null;
  /** Controls shown at the right of the address bar. */
  controls: ReactNode;
}

/** The reviewed page in a browser-style frame. Scripts stay off inside it, like in a captured page. */
export function PagePreview({ url, addressLabel, patches, highlightSelector, controls }: Props) {
  const [doc, setDoc] = useState<Document | null>(null);
  const [isFullScreen, setIsFullScreen] = useState(false);
  const previewRef = useRef<HTMLElement>(null);

  // Keep the button label in step with the browser, which also leaves full screen on Esc.
  useEffect(() => {
    const syncFullScreenState = () => setIsFullScreen(document.fullscreenElement === previewRef.current);
    document.addEventListener('fullscreenchange', syncFullScreenState);
    return () => document.removeEventListener('fullscreenchange', syncFullScreenState);
  }, []);

  const toggleFullScreen = () => {
    if (document.fullscreenElement) {
      void document.exitFullscreen();
    } else {
      void previewRef.current?.requestFullscreen();
    }
  };

  useEffect(() => {
    if (doc) applyPatches(doc, patches, highlightSelector);
  }, [doc, patches, highlightSelector]);

  // Embedded lessons are sized to their content at the width shown here, so none of it is cut off.
  useEffect(() => (doc ? fitEmbeddedFrames(doc) : undefined), [doc]);

  useEffect(() => {
    if (doc && highlightSelector) {
      doc.querySelector(highlightSelector)?.scrollIntoView({ block: 'center' });
    }
  }, [doc, highlightSelector]);

  return (
    <section ref={previewRef} className="preview" aria-label="Page preview">
      <div className="preview-bar">
        <span className="dots" aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
        <span className="address">{addressLabel}</span>
        {controls}
        <button type="button" className="fullscreen-button" onClick={toggleFullScreen}>
          {isFullScreen ? 'Exit full screen' : 'Full screen'}
        </button>
      </div>
      <iframe
        title={addressLabel}
        src={url}
        sandbox="allow-same-origin"
        onLoad={(e) => setDoc(e.currentTarget.contentDocument)}
      />
    </section>
  );
}
