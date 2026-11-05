import type { Patch } from '../domain/review';

const MARKER = 'data-chameleon';
const HIGHLIGHT_CSS = 'outline: 3px solid #b93a0f; outline-offset: 2px;';

type Undo = () => void;
const undos = new WeakMap<Document, Undo[]>();

/** Remembers how to put a change back, so the next call can start from the original page. */
function recordUndo(doc: Document, undo: Undo): void {
  undos.set(doc, [...(undos.get(doc) ?? []), undo]);
}

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
      recordUndo(doc, () => {
        textNode.nodeValue = original;
      });
      return true;
    }
  }
  return false;
}

/** Swaps an element for the given HTML, or for nothing when the HTML is empty. */
function replaceElement(target: Element, html: string): void {
  const doc = target.ownerDocument;
  const template = doc.createElement('template');
  template.innerHTML = html;
  const replacement = Array.from(template.content.childNodes);
  const anchor = doc.createComment(''); // keeps the place when there is nothing to put there
  target.replaceWith(anchor, ...replacement);
  recordUndo(doc, () => {
    replacement.forEach((node) => node.parentNode?.removeChild(node));
    anchor.replaceWith(target);
  });
}

function setStyleAttribute(target: Element, style: string): void {
  const previous = target.getAttribute('style');
  if (style) target.setAttribute('style', style);
  else target.removeAttribute('style');
  recordUndo(target.ownerDocument, () => {
    if (previous === null) target.removeAttribute('style');
    else target.setAttribute('style', previous);
  });
}

/** Puts a document in the state these patches describe, first removing anything added last time. */
export function applyPatches(doc: Document, patches: Patch[], highlightSelector: string | null): void {
  doc.querySelectorAll(`[${MARKER}]`).forEach((el) => el.remove());
  (undos.get(doc) ?? []).reverse().forEach((undo) => undo());
  undos.delete(doc);

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
    if (patch.kind === 'replaceElement') {
      replaceElement(target, patch.html);
      return;
    }
    if (patch.kind === 'setStyle') {
      setStyleAttribute(target, patch.style);
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
