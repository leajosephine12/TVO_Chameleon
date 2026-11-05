/**
 * Embedded lessons (the frames saved in a capture's frames/ folder) are measured when the page is
 * captured, at the capture window's width. In the review preview the same text wraps differently,
 * so a frame saved at that height can cut its content off, or leave a blank gap. These helpers size
 * each frame to its own content here, at the width it is actually shown at.
 *
 * They work because the captured page and the client share one origin (see vite.config.ts).
 */

/** Page rules that cut a frame's content off: a fixed height or hidden overflow around the frame. */
const RELEASE_CLIPPING: Record<string, string> = {
  height: 'auto',
  'max-height': 'none',
  overflow: 'visible',
};

/** The height of everything inside a frame. The frame is collapsed first so that the content can also shrink. */
function measureContentHeight(frame: HTMLIFrameElement, inner: Document): number {
  frame.style.setProperty('height', '0px', 'important');
  const height = Math.ceil(Math.max(inner.documentElement.scrollHeight, inner.body?.scrollHeight ?? 0));
  frame.style.setProperty('height', `${height}px`, 'important');
  return height;
}

/** Lets the page's own boxes around the frame grow with it instead of cutting it off. */
function releaseClippingAncestors(frame: HTMLIFrameElement): void {
  const frameBottom = frame.getBoundingClientRect().bottom;
  for (let box = frame.parentElement; box && box !== box.ownerDocument.body; box = box.parentElement) {
    const clipsFrame = box.getBoundingClientRect().bottom < frameBottom - 1;
    if (!clipsFrame) continue;
    Object.entries(RELEASE_CLIPPING).forEach(([property, value]) =>
      box.style.setProperty(property, value, 'important'),
    );
  }
}

/** Keeps one frame as tall as its content, including when the content changes (tabs, images, text). */
function fitFrame(frame: HTMLIFrameElement, observers: ResizeObserver[]): void {
  const inner = frame.contentDocument;
  if (!inner?.documentElement) return;

  // The frame scrolls inside only as a last resort; the page around it should show everything.
  frame.removeAttribute('scrolling');
  let lastHeight = -1;
  const refit = () => {
    const height = measureContentHeight(frame, inner);
    if (height !== lastHeight) releaseClippingAncestors(frame);
    lastHeight = height;
  };

  refit();
  const observer = new ResizeObserver(refit);
  observer.observe(inner.documentElement);
  if (inner.body) observer.observe(inner.body);
  observers.push(observer);
}

/**
 * Sizes every embedded frame of the previewed page to its content.
 *
 * @returns a function that stops watching, to call when the page is replaced
 */
export function fitEmbeddedFrames(page: Document): () => void {
  const observers: ResizeObserver[] = [];
  const listeners: Array<() => void> = [];

  page.querySelectorAll('iframe').forEach((frame) => {
    const fit = () => fitFrame(frame, observers);
    if (frame.contentDocument?.readyState === 'complete') fit();
    frame.addEventListener('load', fit);
    listeners.push(() => frame.removeEventListener('load', fit));
  });

  return () => {
    listeners.forEach((remove) => remove());
    observers.forEach((observer) => observer.disconnect());
  };
}
