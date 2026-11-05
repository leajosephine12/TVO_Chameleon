import type { Patch, Priority, Suggestion } from '../domain/review';
import layoutRecommendations from './samples/layout_recs_output.json';
import textRecommendations from './samples/text_recs_output.json';

/** One entry of the sample files, which are copies of dyslexia_backend/samples on model-integration. */
interface Recommendation {
  id: string;
  block_id: string;
  type: string;
  original: string;
  suggestion: string;
  rationale: string;
  evidence: string;
  severity: string;
}

/** Where the samples' text blocks are on public/sample-page.html. */
const BLOCKS: Record<string, { selector: string; location: string }> = {
  'p-1': { selector: '.strand-text', location: 'Learning strand text' },
  'p-2': { selector: '.story p', location: 'Student One story' },
};

const TITLES: Record<string, string> = {
  long_sentence: 'Sentence is long',
  difficult_word: 'Wording may be difficult',
  line_spacing: 'Lines are close together',
};

const isCssDeclaration = (text: string) => /^[a-z-]+\s*:/i.test(text);

function patchFor(rec: Recommendation, selector: string): Patch {
  return isCssDeclaration(rec.suggestion)
    ? { kind: 'css', css: `${selector} { ${rec.suggestion} !important; }` }
    : { kind: 'replaceText', selector, find: rec.original, text: rec.suggestion };
}

function toSuggestion(rec: Recommendation): Suggestion {
  const { selector, location } = BLOCKS[rec.block_id];
  return {
    id: rec.id,
    title: TITLES[rec.type],
    location,
    summary: rec.rationale,
    category: 'reading',
    priority: rec.severity as Priority,
    wcagCheck: null,
    evidence: rec.evidence,
    whatWouldChange: isCssDeclaration(rec.suggestion)
      ? `Change the style to "${rec.suggestion}".`
      : 'Replace the text with the suggested wording.',
    before: rec.original,
    after: rec.suggestion,
    targetSelector: selector,
    patches: [patchFor(rec, selector)],
  };
}

export const dyslexiaSuggestions: Suggestion[] = [...textRecommendations, ...layoutRecommendations].map(
  toSuggestion,
);
