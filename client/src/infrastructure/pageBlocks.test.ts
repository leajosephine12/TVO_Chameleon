import { describe, expect, it } from 'vitest';
import { indexBlocks, normalizeHtml } from './pageBlocks';

describe('indexBlocks', () => {
  it('names each captured element by its tag and position, like the backend', () => {
    const blocks = indexBlocks(
      '<body><p data-cid="a">First</p><div><p data-cid="b">Second</p></div><h1 data-cid="c">Title</h1></body>',
    );

    expect(blocks['p-1'].selector).toBe('[data-cid="a"]');
    expect(blocks['p-2'].selector).toBe('[data-cid="b"]');
    expect(blocks['h1-1'].selector).toBe('[data-cid="c"]');
  });

  it('describes a block by its text, its text nodes and its style', () => {
    const blocks = indexBlocks(
      '<body><p data-cid="a" style="color: red">Buy <a href="#">now</a>\n today</p></body>',
    );

    expect(blocks['p-1'].text).toBe('Buy now today');
    expect(blocks['p-1'].textNodes).toEqual(['Buy ', 'now', ' today']);
    expect(blocks['p-1'].style).toBe('color: red');
  });

  it('counts what is inside a <template> but does not offer it, since the page never shows it', () => {
    const blocks = indexBlocks(
      '<body><template><p data-cid="hidden">Not shown</p></template><p data-cid="shown">Shown</p></body>',
    );

    expect(blocks['p-1']).toBeUndefined();
    expect(blocks['p-2'].selector).toBe('[data-cid="shown"]');
  });
});

describe('normalizeHtml', () => {
  // A stray </p> is ignored by the backend's parser (BeautifulSoup) but a browser turns it into an empty
  // paragraph, so the same HTML has 3 paragraphs for the backend and 4 for the browser.
  const sloppy =
    '<body><p data-cid="a">intro</p><div data-cid="b">box</p></div><p data-cid="c">second</p><p data-cid="d">third</p></body>';

  it('writes out the paragraph the browser adds, so a second parser counts the same tree', () => {
    const normalized = normalizeHtml(sloppy);

    expect(normalized).toContain('<div data-cid="b">box<p></p></div>');
  });

  it('gives block ids that match the backend once the normalized HTML is what was analysed', () => {
    const blocks = indexBlocks(normalizeHtml(sloppy));

    // The browser's empty paragraph is p-2, so "second" is p-3 and "third" is p-4.
    expect(blocks['p-3'].selector).toBe('[data-cid="c"]');
    expect(blocks['p-4'].selector).toBe('[data-cid="d"]');
  });

  it('does not change HTML that has already been normalized', () => {
    const once = normalizeHtml(sloppy);

    expect(normalizeHtml(once)).toBe(once);
  });
});
