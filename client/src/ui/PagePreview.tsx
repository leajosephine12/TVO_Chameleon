import { useEffect, useRef, useState, type ReactNode } from 'react';
import type { Patch } from '../domain/review';
import { applyPatches } from './applyPatches';
import { fitEmbeddedFrames } from './fitEmbeddedFrames';

interface Props {
  url: string;
  addressLabel: string;
  patches: Patch[];
  /** The `src` of the frame the patches apply to, or null to apply them to the page itself. */
  targetFrame: string | null;
  highlightSelector: string | null;
  /** Controls shown at the right of the address bar. */
  controls: ReactNode;
}

/** The reviewed page in a browser-style frame. Scripts stay off inside it, like in a captured page. */
export function PagePreview({ url, addressLabel, patches, targetFrame, highlightSelector, controls }: Props) {
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

  // The document the suggestions apply to: the page, or a lesson frame inside it.
  const [targetDoc, setTargetDoc] = useState<Document | null>(null);
  useEffect(() => {
    if (!doc || !targetFrame) {
      setTargetDoc(doc);
      return;
    }
    const frame = doc.querySelector<HTMLIFrameElement>(`iframe[src="${targetFrame}"]`);
    if (!frame) {
      setTargetDoc(null);
      return;
    }
    const useFrameDocument = () => setTargetDoc(frame.contentDocument);
    useFrameDocument();
    frame.addEventListener('load', useFrameDocument); // the frame may still be loading
    return () => frame.removeEventListener('load', useFrameDocument);
  }, [doc, targetFrame]);

  useEffect(() => {
    if (targetDoc) applyPatches(targetDoc, patches, highlightSelector);
  }, [targetDoc, patches, highlightSelector]);

  // Embedded lessons are sized to their content at the width shown here, so none of it is cut off.
  useEffect(() => (doc ? fitEmbeddedFrames(doc) : undefined), [doc]);

  useEffect(() => {
    if (targetDoc && highlightSelector) {
      targetDoc.querySelector(highlightSelector)?.scrollIntoView({ block: 'center' });
    }
  }, [targetDoc, highlightSelector]);

  return (
    <section ref={previewRef} className="preview" aria-label="Page preview">
      <div className="preview-bar">
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
