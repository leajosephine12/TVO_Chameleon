import type { Patch } from '../domain/review';

const MARKER = 'data-chameleon';
const HIGHLIGHT_CSS = 'outline: 3px solid #b93a0f; outline-offset: 2px;';

/** Puts a document in the state these patches describe, first removing anything added last time. */
export function applyPatches(doc: Document, patches: Patch[], highlightSelector: string | null): void {
  doc.querySelectorAll(`[${MARKER}]`).forEach((el) => el.remove());

  const css: string[] = [];
  patches.forEach((patch) => {
    if (patch.kind === 'css') {
      css.push(patch.css);
      return;
    }
    const target = doc.querySelector(patch.selector);
    if (!target) {
      console.warn(`Patch skipped: nothing on the page matches "${patch.selector}"`);
      return;
    }
    const template = doc.createElement('template');
    template.innerHTML = patch.html;
    Array.from(template.content.children).forEach((el) => el.setAttribute(MARKER, ''));
    target[patch.position](template.content);
  });
  if (highlightSelector) css.push(`${highlightSelector} { ${HIGHLIGHT_CSS} }`);

  const style = doc.createElement('style');
  style.setAttribute(MARKER, '');
  style.textContent = css.join('\n');
  doc.head.append(style);
}
