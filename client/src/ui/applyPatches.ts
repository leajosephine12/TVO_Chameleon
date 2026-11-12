import type { Patch } from '../domain/review';

const MARKER = 'data-chameleon';
/** Set on every element the selected suggestion is about, so each one gets the same red outline. */
const HIGHLIGHT_ATTR = 'data-chameleon-highlight';
const HIGHLIGHT_CSS = `[${HIGHLIGHT_ATTR}] { outline: 3px solid #b93a0f !important; outline-offset: 2px !important; }`;

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

/** Swaps an element for the given HTML, or for nothing when the HTML is empty. Returns the new elements. */
function replaceElement(target: Element, html: string): Element[] {
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
  return replacement.filter((node): node is Element => node.nodeType === 1 /* Node.ELEMENT_NODE */);
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

/**
 * Puts a document in the state these patches describe, first removing anything added last time.
 * `highlightSelector` may match several elements, and all of them are outlined, including any that an
 * approved change replaces with new markup.
 */
export function applyPatches(doc: Document, patches: Patch[], highlightSelector: string | null): void {
  doc.querySelectorAll(`[${MARKER}]`).forEach((el) => el.remove());
  (undos.get(doc) ?? []).reverse().forEach((undo) => undo());
  undos.delete(doc);
  doc.querySelectorAll(`[${HIGHLIGHT_ATTR}]`).forEach((el) => el.removeAttribute(HIGHLIGHT_ATTR));

  // Found before the patches run, because a replaced element is no longer on the page to be found after.
  const highlighted = new Set<Element>(highlightSelector ? doc.querySelectorAll(highlightSelector) : []);

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
      const replacements = replaceElement(target, patch.html);
      if (highlighted.has(target)) replacements.forEach((el) => highlighted.add(el));
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
  highlighted.forEach((el) => {
    if (el.isConnected) el.setAttribute(HIGHLIGHT_ATTR, '');
  });
  css.push(HIGHLIGHT_CSS);

  const style = doc.createElement('style');
  style.setAttribute(MARKER, '');
  style.textContent = css.join('\n');
  doc.head.append(style);
}
