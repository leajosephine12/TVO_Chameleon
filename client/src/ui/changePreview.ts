export type Emphasis = 'italic' | 'bold' | 'underline' | null;

export interface ChangePreview {
  /** The words a reviewer reads, without any HTML. */
  text: string;
  /** How the words look on the page, so the before and after can show it. */
  emphasis: Emphasis;
  /** True for CSS such as "font-style: italic", which is shown as code. */
  isCode: boolean;
}

const EMPHASIS_OF_TAG: Record<string, Emphasis> = {
  i: 'italic',
  em: 'italic',
  cite: 'italic',
  dfn: 'italic',
  b: 'bold',
  strong: 'bold',
  u: 'underline',
};

const looksLikeCss = (text: string) => /^[a-z-]+\s*:/i.test(text.trim());

/**
 * How the "Now" or "After" side of a suggestion is shown. The backend sends some sides as HTML, such as
 * `<em data-cid="f0-c49">Why acknowledge?</em>`; a reviewer should see "Why acknowledge?" in italics, not
 * the markup. Plain text and page descriptions are shown as they are.
 */
export function changePreview(side: string): ChangePreview {
  const trimmed = side.trim();
  if (!trimmed.startsWith('<')) return { text: trimmed, emphasis: null, isCode: looksLikeCss(trimmed) };

  const body = new DOMParser().parseFromString(trimmed, 'text/html').body;
  const only = body.children.length === 1 ? body.firstElementChild : null;
  // Several elements, such as a paragraph split in two, are read with a space between them.
  const parts =
    body.children.length > 1
      ? Array.from(body.children, (child) => child.textContent ?? '')
      : [body.textContent ?? ''];
  return {
    text: parts.join(' ').replace(/\s+/g, ' ').trim(),
    emphasis: only ? (EMPHASIS_OF_TAG[only.localName] ?? null) : null,
    isCode: false,
  };
}
