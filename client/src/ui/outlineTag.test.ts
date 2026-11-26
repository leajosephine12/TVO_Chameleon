import { describe, expect, it } from 'vitest';
import { applyPatches } from './applyPatches';
import { placeOutlineTag } from './outlineTag';

function pageWith(body: string): Document {
  const doc = document.implementation.createHTMLDocument('Test');
  doc.body.innerHTML = body;
  return doc;
}

const tagsIn = (doc: Document) =>
  Array.from(doc.querySelectorAll('span[data-chameleon]')).map((tag) => tag.textContent);

describe('placeOutlineTag', () => {
  it('adds one tag with the label when something is outlined', () => {
    const doc = pageWith('<p id="a">One</p><p id="b">Two</p>');
    applyPatches(doc, [], 'p');

    placeOutlineTag(doc, '2 · Italic text');

    expect(tagsIn(doc)).toEqual(['2 · Italic text']);
  });

  it('adds nothing when nothing is outlined', () => {
    const doc = pageWith('<p>One</p>');

    placeOutlineTag(doc, '1 · Italic text');

    expect(tagsIn(doc)).toEqual([]);
  });

  it('takes the tag away again, and so does applying the patches again', () => {
    const doc = pageWith('<p id="a">One</p>');
    applyPatches(doc, [], '#a');

    const remove = placeOutlineTag(doc, '1 · Italic text');
    remove();
    expect(tagsIn(doc)).toEqual([]);

    placeOutlineTag(doc, '1 · Italic text');
    applyPatches(doc, [], null);
    expect(tagsIn(doc)).toEqual([]);
  });
});
