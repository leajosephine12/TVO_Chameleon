import type { ReviewedPage, ReviewVersion } from '../domain/review';

export const samplePage: ReviewedPage = {
  label: 'Sample page · Two Sides to Every Coin',
  url: '/sample-page.html',
};

/** Placeholder suggestions for public/sample-page.html, until real ones come from the backend. */
export const sampleVersions: ReviewVersion[] = [
  {
    id: 'general',
    name: 'General accessibility version',
    shortName: 'general',
    note: 'Ranked for the general version. Approved items go live for every visitor.',
    suggestions: [
      {
        id: 'general-sidebar-links',
        title: 'Six similar links compete for attention',
        location: 'Sidebar activity list',
        summary:
          'Passes WCAG checks, but too many equal choices raise the effort of knowing what to do next.',
        category: 'cognitive',
        priority: 'high',
        wcagCheck: 'pass',
        whatWouldChange:
          'Highlight the current activity with previous and next controls, and let learners expand the full list.',
        before: 'All six activities are listed with the same visual weight.',
        after: 'Only the current activity shows, with a next step and an option to see the full list.',
        targetSelector: '.activity-nav',
        patches: [
          {
            kind: 'css',
            css: `.activity:not(.is-current) { display: none; }
.activities:has(.chameleon-expand input:checked) .activity { display: block; }
.chameleon-expand { display: flex; gap: 8px; align-items: center; padding: 10px 16px; font-size: 13px; font-weight: 700; }
.chameleon-steps { display: flex; justify-content: space-between; gap: 8px; padding: 10px 16px; font-size: 13px; font-weight: 700; }`,
          },
          {
            kind: 'insert',
            selector: '.activities',
            position: 'prepend',
            html: '<label class="chameleon-expand"><input type="checkbox"> Show all 6 activities</label>',
          },
          {
            kind: 'insert',
            selector: '.activity.is-current',
            position: 'after',
            html: '<div class="chameleon-steps"><span>First activity</span><a href="#">Next: Setting Financial Goals</a></div>',
          },
        ],
      },
      {
        id: 'general-tab-contrast',
        title: 'Tab labels fall short on contrast',
        location: 'Lesson tabs',
        summary: 'The grey tab labels are hard to read against the grey tab bar.',
        category: 'wcag',
        priority: 'medium',
        wcagCheck: 'fail',
        whatWouldChange: 'Darken the tab labels so they meet the WCAG AA contrast minimum.',
        before: 'Mid-grey labels on a grey bar.',
        after: 'Dark labels on the same bar, with the current tab in bold.',
        targetSelector: '.lesson-tabs',
        patches: [
          {
            kind: 'css',
            css: `.lesson-tabs a { color: #1f2933; }
.lesson-tabs a.is-current { font-weight: 700; }`,
          },
        ],
      },
      {
        id: 'general-heading-levels',
        title: 'Heading levels look alike',
        location: 'Lesson headings',
        summary:
          'Section and sub-section headings look nearly the same, which hides how the lesson is organized.',
        category: 'cognitive',
        priority: 'medium',
        wcagCheck: 'pass',
        whatWouldChange: 'Make each heading level clearly different in size and weight.',
        before: 'Headings differ by only a few pixels and share one weight.',
        after: 'Section headings are larger and bold, and sub-section headings are clearly smaller.',
        targetSelector: '.lesson-body h2',
        patches: [
          {
            kind: 'css',
            css: `.lesson-body h2 { font-size: 32px; font-weight: 700; }
.lesson-body h3 { font-size: 21px; font-weight: 700; }`,
          },
        ],
      },
      {
        id: 'general-banner-title',
        title: 'Banner title may be part of the image',
        location: 'Lesson banner',
        summary:
          'The title looks drawn into the banner, so assistive technology may not read it as a heading.',
        category: 'wcag',
        priority: 'low',
        wcagCheck: 'review',
        whatWouldChange: 'Show the banner title as real text in a heading.',
        before: 'The words "Minds On" are part of the banner artwork.',
        after: 'The words "Minds On" are a real heading placed over the artwork.',
        targetSelector: '.banner',
        patches: [
          {
            kind: 'css',
            css: `.banner { position: relative; }
.banner-title { display: none; }
.chameleon-banner-title { position: absolute; top: 14px; left: 16px; margin: 0; color: #2563c9; font-size: 52px; font-weight: 700; }`,
          },
          {
            kind: 'insert',
            selector: '.banner',
            position: 'prepend',
            html: '<h2 class="chameleon-banner-title">Minds On</h2>',
          },
        ],
      },
    ],
  },
  {
    id: 'dyslexia',
    name: 'Dyslexia version',
    shortName: 'dyslexia',
    note: "Ranked for the dyslexia version. Approved items go live for visitors who choose it, on top of the general version's approved changes.",
    builtOnVersionId: 'general',
    suggestions: [
      {
        id: 'dyslexia-text-spacing',
        title: 'Lesson text is tightly spaced',
        location: 'Lesson text',
        summary: 'Tight lines and letters make it easier to lose your place while reading.',
        category: 'reading',
        priority: 'high',
        wcagCheck: 'pass',
        whatWouldChange: 'Add space between lines, letters and words in the lesson text.',
        before: 'Compact line, letter and word spacing.',
        after: 'Line height of 1.8, with slightly wider letter and word spacing.',
        targetSelector: '.story',
        patches: [
          {
            kind: 'css',
            css: '.lesson-body p { line-height: 1.8; letter-spacing: 0.03em; word-spacing: 0.1em; }',
          },
        ],
      },
      {
        id: 'dyslexia-chunk-story',
        title: 'Long story has no quick summary',
        location: 'Student One story',
        summary: 'Learners must read the whole paragraph before they know what it is about.',
        category: 'cognitive',
        priority: 'high',
        wcagCheck: 'pass',
        whatWouldChange: 'Add a one-sentence key idea above the story.',
        before: 'The story starts straight away with a long paragraph.',
        after: 'A short key idea appears first, followed by the full story.',
        targetSelector: '.story',
        patches: [
          {
            kind: 'css',
            css: '.chameleon-key { margin: 0 0 14px; padding: 10px 14px; border-left: 4px solid #0b5a4f; background: #e7f3f0; }',
          },
          {
            kind: 'insert',
            selector: '.story',
            position: 'prepend',
            html: '<p class="chameleon-key"><strong>Key idea:</strong> Living far from a store makes groceries harder to afford.</p>',
          },
        ],
      },
      {
        id: 'dyslexia-page-glare',
        title: 'Pure white background can cause glare',
        location: 'Lesson panel',
        summary:
          'Strong contrast between black text and pure white can make words seem to move for some readers.',
        category: 'reading',
        priority: 'medium',
        wcagCheck: 'pass',
        whatWouldChange: 'Use a soft cream background and keep the text dark.',
        before: 'Dark text on pure white.',
        after: 'Dark text on soft cream.',
        targetSelector: '.lesson-body',
        patches: [{ kind: 'css', css: '.lesson-body { background: #fbf6e9; }' }],
      },
      {
        id: 'dyslexia-sidebar-text',
        title: 'Sidebar text is small and dense',
        location: 'Learning strand',
        summary: 'The strand description is a long block of small text.',
        category: 'reading',
        priority: 'medium',
        wcagCheck: 'pass',
        whatWouldChange: 'Increase the size and line spacing of the sidebar text.',
        before: '12px text in a compact block.',
        after: '15px text with more space between lines.',
        targetSelector: '.strand-text',
        patches: [{ kind: 'css', css: '.strand-text { font-size: 15px; line-height: 1.7; }' }],
      },
      {
        id: 'dyslexia-line-length',
        title: 'Lines of text run long',
        location: 'Lesson introduction',
        summary: 'Long lines make it harder to find the start of the next line.',
        category: 'reading',
        priority: 'low',
        wcagCheck: 'pass',
        whatWouldChange: 'Limit lesson text to about 60 characters per line.',
        before: 'Text fills the full width of the lesson.',
        after: 'Text stops at a comfortable reading width.',
        targetSelector: '.intro',
        patches: [{ kind: 'css', css: '.intro p, .lesson-lead { max-width: 60ch; }' }],
      },
    ],
  },
];
