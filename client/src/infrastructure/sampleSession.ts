import type { ReviewedPage, ReviewVersion } from '../domain/review';
import { dyslexiaSuggestions } from './sampleRecommendations';

export const samplePage: ReviewedPage = {
  label: 'Sample page · Two Sides to Every Coin',
  url: '/sample-page.html',
};

/** Suggestions for public/sample-page.html: placeholders for General, the backend team's samples for Dyslexia. */
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
    suggestions: dyslexiaSuggestions,
  },
];
