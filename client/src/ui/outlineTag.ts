import { HIGHLIGHT_ATTR, HIGHLIGHT_COLOUR, MARKER } from './applyPatches';

/**
 * The tag's look. It is set inline and marked important, so the reviewed page's own CSS cannot change it.
 * It sits in the page's top layer of stacking and lets clicks through to the page below.
 */
const TAG_STYLE: Record<string, string> = {
  position: 'absolute',
  'z-index': '2147483647',
  padding: '2px 10px',
  'border-radius': '999px',
  background: HIGHLIGHT_COLOUR,
  color: '#fff',
  font: '700 12px/1.6 Inter, system-ui, -apple-system, "Segoe UI", sans-serif',
  'white-space': 'nowrap',
  'pointer-events': 'none',
  'box-shadow': '0 1px 3px rgb(0 0 0 / 20%)',
};

/** The gap between the tag and the outline: the outline is drawn 2px outside the element and is 3px wide. */
const GAP_ABOVE_OUTLINE = 6;

/**
 * Puts a small tag such as "2 · Italic text" on the corner of the first outlined element in the reviewed
 * page, so the outline can be matched to its suggestion in the panel. The tag is placed again when the page
 * changes size, because the element moves.
 *
 * @returns a function that removes the tag
 */
export function placeOutlineTag(doc: Document, label: string): () => void {
  const outlined = doc.querySelector(`[${HIGHLIGHT_ATTR}]`);
  if (!outlined) return () => undefined;
  // A document without a window (as in tests) has no scrolling or resizing to follow.
  const frameWindow = doc.defaultView;

  const tag = doc.createElement('span');
  tag.setAttribute(MARKER, ''); // removed with everything else the review added, when patches are applied again
  tag.setAttribute('aria-hidden', 'true'); // the panel already says which suggestion is open
  tag.textContent = label;
  Object.entries(TAG_STYLE).forEach(([property, value]) =>
    tag.style.setProperty(property, value, 'important'),
  );
  doc.body.append(tag);

  // Right-aligned with the outline and sitting just above it, so it never covers the outlined words.
  // It stays inside the page's top and left edges.
  const place = () => {
    const box = outlined.getBoundingClientRect();
    const scrollX = frameWindow?.scrollX ?? 0;
    const scrollY = frameWindow?.scrollY ?? 0;
    const top = Math.max(scrollY + 2, box.top + scrollY - tag.offsetHeight - GAP_ABOVE_OUTLINE);
    const left = Math.max(scrollX + 4, box.right + scrollX - tag.offsetWidth);
    tag.style.setProperty('top', `${top}px`, 'important');
    tag.style.setProperty('left', `${left}px`, 'important');
  };
  place();
  // Images loading, a lesson tab opening or the window resizing all move the element.
  frameWindow?.addEventListener('resize', place);
  const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(place);
  observer?.observe(doc.body);

  return () => {
    frameWindow?.removeEventListener('resize', place);
    observer?.disconnect();
    tag.remove();
  };
}
