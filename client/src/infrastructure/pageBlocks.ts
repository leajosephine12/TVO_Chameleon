import type { LessonTab } from '../domain/review';

/** Attribute the capture tool puts on every element of a saved page. It never changes, so it can point at one element. */
const CAPTURE_ID_ATTRIBUTE = 'data-cid';

/** The tab a block is in, so a suggestion can be shown with the tab it is about. */
const TAB_PANEL_SELECTOR = '[data-tab-panel]';

/** One block of the analysed page, as the backend names it. */
export interface PageBlock {
  /** Selector for this element in the captured page. */
  selector: string;
  tag: string;
  /** The element's text with runs of whitespace collapsed. */
  text: string;
  /**
   * The text of each separate text node inside the element, with each run of whitespace turned into one
   * space (the same way `replaceText` in ui/applyPatches.ts reads them). Text interrupted by a link or other
   * tag is split across several of these, and only one node's text can be replaced at a time.
   */
  textNodes: string[];
  /** The element's style attribute, or null if it has none. */
  style: string | null;
  /** The id of the lesson tab the element is in, or null if it is not inside a tab. */
  tabId: string | null;
}

export const collapseWhitespace = (text: string): string => text.replace(/\s+/g, ' ').trim();

/** The text a piece of HTML shows, with whitespace collapsed. */
export function textOfHtml(html: string): string {
  const page = new DOMParser().parseFromString(html, 'text/html');
  return collapseWhitespace(page.body.textContent ?? '');
}

/** The text of every text node under an element, each with its whitespace runs turned into one space. */
function textNodesOf(element: Element): string[] {
  const walker = element.ownerDocument.createTreeWalker(element, 4 /* NodeFilter.SHOW_TEXT */);
  const texts: string[] = [];
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    texts.push((node.nodeValue ?? '').replace(/\s+/g, ' '));
  }
  return texts;
}

/**
 * Writes a page out the way the browser parsed it.
 *
 * Browsers and the backend's parser (BeautifulSoup) build different trees from sloppy HTML: a stray
 * `</p>` becomes an empty paragraph in a browser and is ignored by BeautifulSoup, and a `<table>` row
 * gets a `<tbody>` only in the browser. Counting tags in two different trees gives different block ids.
 * Once the browser's tree has been written out, it is well-formed, so both parsers build the same tree.
 * Send this string to the backend and give the same string to `indexBlocks`.
 */
export function normalizeHtml(html: string): string {
  const page = new DOMParser().parseFromString(html, 'text/html');
  return `<!doctype html>${page.documentElement.outerHTML}`;
}

/**
 * Finds the element each backend block id stands for.
 *
 * The backend names a block "<tag>-<n>": the n-th such tag in the HTML it was sent, counting every
 * element in document order (dyslexia_engine/app/adaptation_engine.py, `_index_blocks`). This counts
 * the same way, so the HTML given here must be the exact HTML that was sent for analysis, as returned by
 * `normalizeHtml`.
 *
 * @returns blocks keyed by block id, for example { "p-4": { selector: '[data-cid="f0-c130"]', ... } }
 */
export function indexBlocks(html: string): Record<string, PageBlock> {
  const page = new DOMParser().parseFromString(html, 'text/html');
  const countPerTag: Record<string, number> = {};
  const blocks: Record<string, PageBlock> = {};

  /** `insideTemplate`: the backend counts the contents of <template>, but the browser never shows them. */
  const visit = (parent: ParentNode, insideTemplate: boolean): void => {
    for (const element of Array.from(parent.children)) {
      // The backend's parser lower-cases tag names, so SVG names such as "linearGradient" are counted lower-case.
      const tag = element.localName.toLowerCase();
      countPerTag[tag] = (countPerTag[tag] ?? 0) + 1;

      const captureId = element.getAttribute(CAPTURE_ID_ATTRIBUTE);
      if (captureId && !insideTemplate) {
        blocks[`${tag}-${countPerTag[tag]}`] = {
          selector: `[${CAPTURE_ID_ATTRIBUTE}="${captureId}"]`,
          tag,
          text: collapseWhitespace(element.textContent ?? ''),
          textNodes: textNodesOf(element),
          style: element.getAttribute('style'),
          tabId: element.closest(TAB_PANEL_SELECTOR)?.id || null,
        };
      }

      visit(element, insideTemplate);
      if (element instanceof HTMLTemplateElement) visit(element.content, true);
    }
  };
  visit(page, false);

  return blocks;
}

/**
 * The tabs of a captured lesson, in the order the lesson shows them.
 *
 * The capture tool marks each tab link with `data-tab-trigger="<panel id>"` and each panel with
 * `data-tab-panel` (capture.js), because a saved page has no scripts to switch tabs. A trigger without a
 * matching panel is left out.
 */
export function readLessonTabs(html: string): LessonTab[] {
  const page = new DOMParser().parseFromString(html, 'text/html');
  const panelIds = new Set(Array.from(page.querySelectorAll(TAB_PANEL_SELECTOR), (panel) => panel.id));
  const orderOf = (trigger: Element) => Number(trigger.getAttribute('data-tab-order') ?? Infinity);

  const tabs = new Map<string, LessonTab>();
  Array.from(page.querySelectorAll('[data-tab-trigger]'))
    .sort((a, b) => orderOf(a) - orderOf(b))
    .forEach((trigger) => {
      const id = trigger.getAttribute('data-tab-trigger') ?? '';
      if (panelIds.has(id) && !tabs.has(id)) {
        tabs.set(id, {
          id,
          label: collapseWhitespace(trigger.textContent ?? '') || id,
        });
      }
    });
  return Array.from(tabs.values());
}
