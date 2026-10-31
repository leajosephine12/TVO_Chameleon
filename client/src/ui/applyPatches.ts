import type { Patch } from '../domain/review';

const MARKER = 'data-chameleon';
const HIGHLIGHT_CSS = 'outline: 3px solid #b93a0f; outline-offset: 2px;';

type Undo = () => void;
const textUndos = new WeakMap<Document, Undo[]>();

/** Swaps only the matching words, so the links and styling around them stay as they were. */
function replaceText(target: Element, find: string, text: string): boolean {
  const doc = target.ownerDocument;
  const walker = doc.createTreeWalker(target, 4 /* NodeFilter.SHOW_TEXT */);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const textNode = node;
    const original = textNode.nodeValue ?? '';
    const normalized = original.replace(/\s+/g, ' ');
    if (normalized.includes(find)) {
      textNode.nodeValue = normalized.replace(find, () => text);
      textUndos.set(doc, [
        ...(textUndos.get(doc) ?? []),
        () => {
          textNode.nodeValue = original;
        },
      ]);
      return true;
    }
  }
  return false;
}

/** Puts a document in the state these patches describe, first removing anything added last time. */
export function applyPatches(doc: Document, patches: Patch[], highlightSelector: string | null): void {
  doc.querySelectorAll(`[${MARKER}]`).forEach((el) => el.remove());
  (textUndos.get(doc) ?? []).reverse().forEach((undo) => undo());
  textUndos.delete(doc);

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
    if (patch.kind === 'replaceText') {
      if (!replaceText(target, patch.find, patch.text)) {
        console.warn(`Patch skipped: "${patch.selector}" does not contain the text to replace`);
      }
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
