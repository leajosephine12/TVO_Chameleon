import type { Recommendation } from '../domain/analysis';
import type { Patch, Priority, Suggestion } from '../domain/review';
import { collapseWhitespace, type PageBlock } from './pageBlocks';

/** Recommendations that describe the whole page. Their CSS comes from the backend's /adapted call. */
const PAGE_WIDE_TYPES = ['typography', 'spacing', 'color', 'layout', 'emphasis'];

const TITLES: Record<string, string> = {
  italic_text: 'Italic text',
  underline_text: 'Underlined text',
  inline_style: 'Style the guidelines avoid',
  typography: 'Font and text size',
  spacing: 'Letter, word and line spacing',
  color: 'Text and background colours',
  layout: 'Columns and line length',
  emphasis: 'Italics and underlines in the page CSS',
  long_sentence: 'Sentence is long',
  difficult_word: 'Wording may be difficult',
  line_spacing: 'Lines are close together',
};

const isCssDeclaration = (text: string) => /^[a-z-]+\s*:/i.test(text);

/** Icon fonts use <i> tags, so the backend reports them as italics. There is no text in them to restyle. */
const hasNoText = (block: PageBlock) => block.text === '';

/**
 * The change a recommendation makes once it is approved, or null when it cannot be shown on this page.
 * Which kind of change depends on what the backend put in `original` and `suggestion` for this type.
 */
function patchFor(
  rec: Recommendation,
  block: PageBlock | undefined,
  pageCss: Record<string, string>,
): Patch | null {
  if (PAGE_WIDE_TYPES.includes(rec.type)) {
    const css = pageCss[rec.id];
    return css ? { kind: 'css', css } : null;
  }
  if (!block || hasNoText(block)) return null;

  switch (rec.type) {
    case 'italic_text':
    case 'underline_text':
      // `suggestion` is the element's replacement HTML, for example <strong>…</strong>.
      return { kind: 'replaceElement', selector: block.selector, html: rec.suggestion };
    case 'inline_style':
      // `suggestion` is the new value of the style attribute.
      return { kind: 'setStyle', selector: block.selector, style: rec.suggestion };
    case 'line_spacing':
      return isCssDeclaration(rec.suggestion)
        ? { kind: 'css', css: `${block.selector} { ${rec.suggestion} !important; }` }
        : null;
    case 'long_sentence':
    case 'difficult_word':
      // The model works from the page text, so the sentence must really be in this block.
      return block.text.includes(collapseWhitespace(rec.original))
        ? { kind: 'replaceText', selector: block.selector, find: rec.original, text: rec.suggestion }
        : null;
    default:
      return null;
  }
}

function describeChange(rec: Recommendation, patch: Patch): string {
  switch (patch.kind) {
    case 'replaceElement':
      return 'Replace the element with the suggested markup.';
    case 'setStyle':
      return patch.style
        ? `Change the element's style to "${patch.style}".`
        : "Remove the element's inline style.";
    case 'replaceText':
      return 'Replace the text with the suggested wording.';
    default:
      return PAGE_WIDE_TYPES.includes(rec.type) ? rec.suggestion : `Add the style "${rec.suggestion}".`;
  }
}

function toSuggestion(rec: Recommendation, patch: Patch, block: PageBlock | undefined): Suggestion {
  const isPageWide = PAGE_WIDE_TYPES.includes(rec.type);
  return {
    id: rec.id,
    title: TITLES[rec.type] ?? rec.type,
    location: isPageWide ? 'Whole page' : (block?.tag ?? rec.block_id),
    summary: rec.rationale,
    category: 'reading',
    priority: rec.severity as Priority,
    wcagCheck: null,
    evidence: rec.evidence,
    whatWouldChange: describeChange(rec, patch),
    before: rec.original,
    after: rec.suggestion || '(removed)',
    targetSelector: block?.selector ?? null,
    patches: [patch],
  };
}

/**
 * Turns the backend's recommendations into suggestions for the review panel.
 * A recommendation is left out when it cannot be shown on the page, for example when its block is not
 * there or the model quoted text the block does not contain, so every suggestion shown can be previewed.
 */
export function suggestionsFromRecommendations(
  recommendations: Recommendation[],
  blocks: Record<string, PageBlock>,
  pageCss: Record<string, string>,
): Suggestion[] {
  return recommendations.flatMap((rec) => {
    const block = blocks[rec.block_id];
    const patch = patchFor(rec, block, pageCss);
    return patch ? [toSuggestion(rec, patch, block)] : [];
  });
}

/** True when the recommendation needs the backend's CSS instead of an element on the page. */
export const isPageWide = (rec: Recommendation): boolean => PAGE_WIDE_TYPES.includes(rec.type);
