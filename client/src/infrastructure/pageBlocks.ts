/** Attribute the capture tool puts on every element of a saved page. It never changes, so it can point at one element. */
const CAPTURE_ID_ATTRIBUTE = 'data-cid';

/** One block of the analysed page, as the backend names it. */
export interface PageBlock {
  /** Selector for this element in the captured page. */
  selector: string;
  tag: string;
  /** The element's text with runs of whitespace collapsed. */
  text: string;
}

export const collapseWhitespace = (text: string): string => text.replace(/\s+/g, ' ').trim();

/**
 * Finds the element each backend block id stands for.
 *
 * The backend names a block "<tag>-<n>": the n-th such tag in the HTML it was sent, counting every
 * element in document order (dyslexia_engine/app/adaptation_engine.py, `_index_blocks`). This counts
 * the same way, so the HTML given here must be the HTML that was sent for analysis.
 *
 * @returns blocks keyed by block id, for example { "p-4": { selector: '[data-cid="f0-c130"]', ... } }
 */
export function indexBlocks(html: string): Record<string, PageBlock> {
  const page = new DOMParser().parseFromString(html, 'text/html');
  const countPerTag: Record<string, number> = {};
  const blocks: Record<string, PageBlock> = {};

  page.querySelectorAll('*').forEach((element) => {
    // The backend's parser lower-cases tag names, so SVG names such as "linearGradient" are counted lower-case.
    const tag = element.localName.toLowerCase();
    countPerTag[tag] = (countPerTag[tag] ?? 0) + 1;

    const captureId = element.getAttribute(CAPTURE_ID_ATTRIBUTE);
    if (!captureId) return;
    blocks[`${tag}-${countPerTag[tag]}`] = {
      selector: `[${CAPTURE_ID_ATTRIBUTE}="${captureId}"]`,
      tag,
      text: collapseWhitespace(element.textContent ?? ''),
    };
  });

  return blocks;
}
