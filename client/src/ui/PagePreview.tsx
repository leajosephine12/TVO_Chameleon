import { useEffect, useRef, useState, type ReactNode } from 'react';
import type { Patch } from '../domain/review';
import { applyPatches } from './applyPatches';
import { fitEmbeddedFrames } from './fitEmbeddedFrames';
import { placeOutlineTag } from './outlineTag';

interface Props {
  url: string;
  addressLabel: string;
  patches: Patch[];
  /** The `src` of the frame the patches apply to, or null to apply them to the page itself. */
  targetFrame: string | null;
  highlightSelector: string | null;
  /** The tag shown on the outline, such as "2 · Italic text", or null for none. */
  highlightLabel: string | null;
  /** The lesson tab to show, or null to leave the lesson on the tab it is on. */
  tabId: string | null;
  /** Called with the id a tab link inside the lesson switched to, such as "action". */
  onLessonTabChange: (tabId: string) => void;
  /** Controls shown at the right of the address bar. */
  controls: ReactNode;
}

/**
 * Scrolls the preview so the element sits in the middle of it. Unlike `scrollIntoView`, this moves only
 * the preview: on a narrow screen the app itself scrolls too, and it must not jump to the preview each
 * time a suggestion is opened. The element can be inside a lesson frame within the previewed page.
 */
function scrollToCentre(previewDoc: Document, element: Element): void {
  const previewWindow = previewDoc.defaultView;
  if (!previewWindow) return;
  const box = element.getBoundingClientRect();
  // Add the offset of each frame between the element and the preview, to get its place in the preview.
  let top = box.top;
  for (let frameWindow = element.ownerDocument.defaultView; frameWindow && frameWindow !== previewWindow;) {
    const frame = frameWindow.frameElement;
    if (!frame) return;
    top += frame.getBoundingClientRect().top;
    frameWindow = frame.ownerDocument.defaultView;
  }
  previewWindow.scrollBy({ top: top - (previewWindow.innerHeight - box.height) / 2 });
}

/** The reviewed page in a browser-style frame. Scripts stay off inside it, like in a captured page. */
export function PagePreview({
  url,
  addressLabel,
  patches,
  targetFrame,
  highlightSelector,
  highlightLabel,
  tabId,
  onLessonTabChange,
  controls,
}: Props) {
  const [doc, setDoc] = useState<Document | null>(null);
  const [isFullScreen, setIsFullScreen] = useState(false);
  const previewRef = useRef<HTMLElement>(null);

  // Keep the button label in step with the browser, which also leaves full screen on Esc.
  useEffect(() => {
    const syncFullScreenState = () => setIsFullScreen(document.fullscreenElement === previewRef.current);
    document.addEventListener('fullscreenchange', syncFullScreenState);
    return () => document.removeEventListener('fullscreenchange', syncFullScreenState);
  }, []);

  // iPhone Safari has no full screen for page elements, so the button is left out there.
  const canFullScreen = document.fullscreenEnabled === true;

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

  // A captured lesson has no scripts, so its tabs are links to "#<panel id>" and the browser shows the panel
  // that is the target of the address. Setting the address switches the tab, like clicking the link.
  // `replace` keeps the switch out of the browser history, so Back still leaves the app instead of
  // stepping through lesson tabs. The address is made whole first: a bare "#action" would be read against
  // this app's address, not the lesson's, and load the app into the preview.
  useEffect(() => {
    const frameWindow = targetDoc?.defaultView;
    if (tabId && frameWindow && frameWindow.location.hash !== `#${tabId}`) {
      frameWindow.location.replace(new URL(`#${tabId}`, frameWindow.location.href).href);
    }
  }, [targetDoc, tabId]);

  // Clicking a tab inside the lesson changes the address too, so the review panel follows it.
  useEffect(() => {
    const frameWindow = targetDoc?.defaultView;
    if (!frameWindow) return undefined;
    const reportTab = () => onLessonTabChange(frameWindow.location.hash.slice(1));
    frameWindow.addEventListener('hashchange', reportTab);
    return () => frameWindow.removeEventListener('hashchange', reportTab);
  }, [targetDoc, onLessonTabChange]);

  useEffect(() => {
    if (targetDoc) applyPatches(targetDoc, patches, highlightSelector);
  }, [targetDoc, patches, highlightSelector]);

  // After the patches, because applying them again takes the tag away with everything else the review added.
  useEffect(
    () =>
      targetDoc && highlightSelector && highlightLabel
        ? placeOutlineTag(targetDoc, highlightLabel)
        : undefined,
    [targetDoc, patches, highlightSelector, highlightLabel],
  );

  // Embedded lessons are sized to their content at the width shown here, so none of it is cut off.
  useEffect(() => (doc ? fitEmbeddedFrames(doc) : undefined), [doc]);

  useEffect(() => {
    const outlined = highlightSelector ? targetDoc?.querySelector('[data-chameleon-highlight]') : null;
    if (outlined && doc) scrollToCentre(doc, outlined);
  }, [doc, targetDoc, highlightSelector]);

  return (
    <section ref={previewRef} className="preview" aria-label="Page preview">
      <div className="preview-bar">
        <span className="address">{addressLabel}</span>
        {controls}
        {canFullScreen && (
          <button type="button" className="fullscreen-button" onClick={toggleFullScreen}>
            <svg
              aria-hidden="true"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" />
            </svg>
            {/* On phones only the icon shows; the words stay for screen readers. */}
            <span className="label-wide-only">{isFullScreen ? 'Exit full screen' : 'Full screen'}</span>
          </button>
        )}
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
