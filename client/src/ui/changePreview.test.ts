import { describe, expect, it } from 'vitest';
import { changePreview } from './changePreview';

describe('changePreview', () => {
  it('shows the words of an italic element in italics, without the markup', () => {
    expect(changePreview('<em data-cid="f0-c49">Why acknowledge?</em>')).toEqual({
      text: 'Why acknowledge?',
      emphasis: 'italic',
      isCode: false,
    });
  });

  it('shows a bold replacement in bold', () => {
    expect(changePreview('<strong>Why acknowledge?</strong>').emphasis).toBe('bold');
  });

  it('shows an underline as underlined', () => {
    expect(changePreview('<u>chloroplasts</u>').emphasis).toBe('underline');
  });

  it('keeps plain text as it is', () => {
    expect(changePreview('their parents earn a limited income.')).toEqual({
      text: 'their parents earn a limited income.',
      emphasis: null,
      isCode: false,
    });
  });

  it('marks CSS so it can be shown as code', () => {
    expect(changePreview('font-style: italic;').isCode).toBe(true);
  });

  it('reads several elements with a space between them, and gives them no emphasis', () => {
    expect(changePreview('<p>One.</p><p>Two.</p>')).toMatchObject({ text: 'One. Two.', emphasis: null });
  });
});
