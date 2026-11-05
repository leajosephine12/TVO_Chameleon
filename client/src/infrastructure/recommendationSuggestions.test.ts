import { describe, expect, it } from 'vitest';
import type { Recommendation } from '../domain/analysis';
import { indexBlocks } from './pageBlocks';
import { suggestionsFromRecommendations } from './recommendationSuggestions';

function recommendation(overrides: Partial<Recommendation>): Recommendation {
  return {
    id: 'r1',
    block_id: 'p-1',
    type: 'long_sentence',
    original: '',
    suggestion: '',
    rationale: 'Because.',
    evidence: 'Guideline',
    severity: 'low',
    status: 'pending',
    ...overrides,
  };
}

const suggestionsFor = (html: string, recs: Recommendation[], pageCss: Record<string, string> = {}) =>
  suggestionsFromRecommendations(recs, indexBlocks(`<body>${html}</body>`), pageCss);

describe('italic and underline recommendations', () => {
  it('replace the element when it is the tag the backend meant and the text is the same', () => {
    const [suggestion] = suggestionsFor('<p>Read <em data-cid="a">this</em></p>', [
      recommendation({
        block_id: 'em-1',
        type: 'italic_text',
        original: '<em>this</em>',
        suggestion: '<strong>this</strong>',
      }),
    ]);

    expect(suggestion.patches).toEqual([
      { kind: 'replaceElement', selector: '[data-cid="a"]', html: '<strong>this</strong>' },
    ]);
  });

  it('are left out when the block is not an italic tag, as when ids have drifted', () => {
    const suggestions = suggestionsFor('<p data-cid="a">this</p>', [
      recommendation({ block_id: 'p-1', type: 'italic_text', suggestion: '<strong>this</strong>' }),
    ]);

    expect(suggestions).toEqual([]);
  });

  it('are left out when the replacement has different text than the block', () => {
    const suggestions = suggestionsFor('<em data-cid="a">this</em>', [
      recommendation({
        block_id: 'em-1',
        type: 'italic_text',
        suggestion: '<strong>something else</strong>',
      }),
    ]);

    expect(suggestions).toEqual([]);
  });

  it('accept <u> for underlines only', () => {
    const html = '<u data-cid="a">this</u>';
    const underline = recommendation({ block_id: 'u-1', type: 'underline_text', suggestion: 'this' });

    expect(suggestionsFor(html, [underline])).toHaveLength(1);
    expect(suggestionsFor(html, [{ ...underline, type: 'italic_text' }])).toEqual([]);
  });
});

describe('inline style recommendations', () => {
  it('set the style when the block has the style the backend saw', () => {
    const [suggestion] = suggestionsFor('<p data-cid="a" style="text-decoration: underline;">Text</p>', [
      recommendation({ type: 'inline_style', original: 'text-decoration: underline;', suggestion: '' }),
    ]);

    expect(suggestion.patches).toEqual([{ kind: 'setStyle', selector: '[data-cid="a"]', style: '' }]);
  });

  it('are left out when the block has a different style or none', () => {
    const rec = recommendation({ type: 'inline_style', original: 'text-decoration: underline;' });

    expect(suggestionsFor('<p data-cid="a" style="color: red">Text</p>', [rec])).toEqual([]);
    expect(suggestionsFor('<p data-cid="a">Text</p>', [rec])).toEqual([]);
  });
});

describe('text recommendations', () => {
  const rewrite = { type: 'long_sentence', suggestion: 'Short.' };

  it('replace a sentence that sits in one piece of the block', () => {
    const [suggestion] = suggestionsFor('<p data-cid="a">Intro. A long sentence here. Outro.</p>', [
      recommendation({ ...rewrite, original: 'A long sentence here.' }),
    ]);

    expect(suggestion.patches).toEqual([
      { kind: 'replaceText', selector: '[data-cid="a"]', find: 'A long sentence here.', text: 'Short.' },
    ]);
  });

  it('are left out when a link splits the sentence, because only one text node can be replaced', () => {
    const suggestions = suggestionsFor('<p data-cid="a">A long <a href="#">linked</a> sentence.</p>', [
      recommendation({ ...rewrite, original: 'A long linked sentence.' }),
    ]);

    expect(suggestions).toEqual([]);
  });

  it('look for the sentence with its whitespace collapsed, as the page text is', () => {
    const [suggestion] = suggestionsFor('<p data-cid="a">A long  sentence\nhere.</p>', [
      recommendation({ ...rewrite, original: 'A long  sentence\nhere.' }),
    ]);

    expect(suggestion.patches[0]).toMatchObject({ kind: 'replaceText', find: 'A long sentence here.' });
  });

  it('are left out when the model quoted text that is not in the block', () => {
    const suggestions = suggestionsFor('<p data-cid="a">Something else.</p>', [
      recommendation({ ...rewrite, original: 'A long sentence here.' }),
    ]);

    expect(suggestions).toEqual([]);
  });
});

describe('page-wide recommendations', () => {
  it('use the CSS the backend produced and point at no element', () => {
    const [suggestion] = suggestionsFor(
      '<p data-cid="a">Text</p>',
      [recommendation({ id: 'r7', block_id: 'page', type: 'color' })],
      { r7: 'body { color: #3a3a3a; }' },
    );

    expect(suggestion.patches).toEqual([{ kind: 'css', css: 'body { color: #3a3a3a; }' }]);
    expect(suggestion.targetSelector).toBeNull();
  });

  it('are left out when the backend produced no CSS for them', () => {
    expect(
      suggestionsFor('<p data-cid="a">Text</p>', [recommendation({ block_id: 'page', type: 'color' })]),
    ).toEqual([]);
  });
});
