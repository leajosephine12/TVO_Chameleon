import { describe, expect, it } from 'vitest';
import type { Patch } from '../domain/review';
import { applyPatches } from './applyPatches';

/** A page with the given body, like a captured page whose elements carry data-cid. */
function pageWith(body: string): Document {
  const doc = document.implementation.createHTMLDocument('Test');
  doc.body.innerHTML = body;
  return doc;
}

const apply = (doc: Document, patches: Patch[]) => applyPatches(doc, patches, null);

describe('replaceText', () => {
  it('changes only the matching words and keeps the link around them', () => {
    const doc = pageWith('<p data-cid="a">A long sentence. See <a href="#">this link</a>.</p>');

    apply(doc, [
      { kind: 'replaceText', selector: '[data-cid="a"]', find: 'A long sentence.', text: 'Short.' },
    ]);

    expect(doc.body.innerHTML).toBe('<p data-cid="a">Short. See <a href="#">this link</a>.</p>');
  });

  it('finds text whose whitespace was collapsed', () => {
    const doc = pageWith('<p data-cid="a">A long  sentence\nhere.</p>');

    apply(doc, [
      { kind: 'replaceText', selector: '[data-cid="a"]', find: 'A long sentence here.', text: 'Short.' },
    ]);

    expect(doc.querySelector('p')?.textContent).toBe('Short.');
  });

  it('cannot match text that a link splits, which is why such suggestions are not offered', () => {
    const doc = pageWith('<p data-cid="a">A long <a href="#">linked</a> sentence.</p>');

    apply(doc, [
      { kind: 'replaceText', selector: '[data-cid="a"]', find: 'A long linked sentence.', text: 'Short.' },
    ]);

    expect(doc.querySelector('p')?.textContent).toBe('A long linked sentence.');
  });
});

describe('replaceElement', () => {
  it('swaps the element and puts it back when the patches change', () => {
    const doc = pageWith('<p>Read <em data-cid="a">this</em> now</p>');

    apply(doc, [{ kind: 'replaceElement', selector: '[data-cid="a"]', html: '<strong>this</strong>' }]);
    expect(doc.querySelector('em')).toBeNull();
    expect(doc.querySelector('p')?.innerHTML).toContain('<strong>this</strong> now');

    apply(doc, []);
    expect(doc.body.innerHTML).toBe('<p>Read <em data-cid="a">this</em> now</p>');
  });

  it('removes the element, keeping its place, when the replacement is empty', () => {
    const doc = pageWith('<p>Read <em data-cid="a">this</em> now</p>');

    apply(doc, [{ kind: 'replaceElement', selector: '[data-cid="a"]', html: '' }]);
    expect(doc.querySelector('em')).toBeNull();

    apply(doc, []);
    expect(doc.querySelector('em')?.textContent).toBe('this');
  });
});

describe('setStyle', () => {
  it('sets or removes the style attribute and restores it afterwards', () => {
    const doc = pageWith('<p data-cid="a" style="text-decoration: underline;">Text</p>');
    const p = () => doc.querySelector('p');

    apply(doc, [{ kind: 'setStyle', selector: '[data-cid="a"]', style: '' }]);
    expect(p()?.hasAttribute('style')).toBe(false);

    apply(doc, []);
    expect(p()?.getAttribute('style')).toBe('text-decoration: underline;');
  });
});

describe('highlight', () => {
  const outlined = (doc: Document) => Array.from(doc.querySelectorAll('[data-chameleon-highlight]'));

  it('outlines every element the selector matches', () => {
    const doc = pageWith('<h2 class="s">One</h2><p>Text</p><h2 class="s">Two</h2>');

    applyPatches(doc, [], '.s');

    expect(outlined(doc).map((el) => el.textContent)).toEqual(['One', 'Two']);
  });

  it('outlines the new element when an approved change replaces the highlighted one', () => {
    const doc = pageWith('<p><i data-cid="a">Key idea</i></p>');
    const patches: Patch[] = [
      { kind: 'replaceElement', selector: '[data-cid="a"]', html: '<strong>Key idea</strong>' },
    ];

    applyPatches(doc, patches, '[data-cid="a"]');

    expect(outlined(doc).map((el) => el.outerHTML)).toEqual([
      '<strong data-chameleon-highlight="">Key idea</strong>',
    ]);
  });

  it('removes the outline when a different suggestion is selected', () => {
    const doc = pageWith('<h2 id="a">One</h2><h2 id="b">Two</h2>');

    applyPatches(doc, [], '#a');
    applyPatches(doc, [], '#b');

    expect(outlined(doc).map((el) => el.id)).toEqual(['b']);
  });
});
