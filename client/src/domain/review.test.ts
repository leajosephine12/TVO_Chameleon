import { describe, expect, it } from 'vitest';
import {
  groupSuggestions,
  standardLessonTabs,
  suggestionsInGroup,
  WHOLE_PAGE_GROUP_ID,
  type Suggestion,
} from './review';

const tabs = [
  { id: 'mindsOn', label: 'Minds On' },
  { id: 'action', label: 'Action' },
];

/** A suggestion with only what grouping looks at. */
const suggestion = (id: string, tabId: string | null): Suggestion => ({
  id,
  title: id,
  location: 'Paragraph',
  summary: '',
  category: 'reading',
  priority: 'low',
  wcagCheck: null,
  whatWouldChange: '',
  before: '',
  after: '',
  targetSelector: null,
  tabId,
  patches: [],
});

describe('standardLessonTabs', () => {
  const standard = [
    { id: 'mindsOn', label: 'Minds On' },
    { id: 'action', label: 'Action' },
    { id: 'consolidation', label: 'Consolidation' },
  ];

  it('keeps the three tabs of a learning activity, in the lesson order', () => {
    expect(standardLessonTabs(standard)).toEqual(standard);
  });

  it('ignores letter case and drops any other tab', () => {
    const withExtra = [
      { id: 'goals', label: 'Goals' },
      ...standard.map((t) => ({ ...t, label: t.label.toUpperCase() })),
    ];

    expect(standardLessonTabs(withExtra).map((tab) => tab.id)).toEqual([
      'mindsOn',
      'action',
      'consolidation',
    ]);
  });

  it('gives no tabs unless all three are there, so the suggestions stay in one list', () => {
    expect(standardLessonTabs(standard.slice(0, 2))).toEqual([]);
    expect(
      standardLessonTabs([
        { id: 'a', label: 'Intro' },
        { id: 'b', label: 'Quiz' },
      ]),
    ).toEqual([]);
    expect(standardLessonTabs([])).toEqual([]);
  });
});

describe('groupSuggestions', () => {
  const suggestions = [
    suggestion('a', 'mindsOn'),
    suggestion('b', 'action'),
    suggestion('c', 'action'),
    suggestion('d', null),
  ];

  it('puts the whole page first, then each tab with its count', () => {
    expect(groupSuggestions(tabs, suggestions)).toEqual([
      { id: WHOLE_PAGE_GROUP_ID, label: 'Whole page', count: 1 },
      { id: 'mindsOn', label: 'Minds On', count: 1 },
      { id: 'action', label: 'Action', count: 2 },
    ]);
  });

  it('leaves out the whole-page group when nothing applies to the whole page', () => {
    const groups = groupSuggestions(tabs, [suggestion('a', 'mindsOn')]);

    expect(groups.map((g) => g.id)).toEqual(['mindsOn', 'action']);
  });

  it('keeps a tab with no suggestions, so every tab of the lesson can be opened', () => {
    expect(groupSuggestions(tabs, [suggestion('a', 'mindsOn')])[1]).toEqual({
      id: 'action',
      label: 'Action',
      count: 0,
    });
  });

  it('makes no groups for a lesson without tabs', () => {
    expect(groupSuggestions([], suggestions)).toEqual([]);
  });
});

describe('suggestionsInGroup', () => {
  const suggestions = [suggestion('a', 'mindsOn'), suggestion('b', 'action'), suggestion('c', null)];
  const groups = groupSuggestions(tabs, suggestions);

  it('returns the suggestions of one tab', () => {
    expect(suggestionsInGroup(suggestions, groups, 'action').map((s) => s.id)).toEqual(['b']);
  });

  it('returns the whole-page suggestions for the whole-page group', () => {
    expect(suggestionsInGroup(suggestions, groups, WHOLE_PAGE_GROUP_ID).map((s) => s.id)).toEqual(['c']);
  });

  it('returns every suggestion when there are no groups', () => {
    expect(suggestionsInGroup(suggestions, [], '')).toHaveLength(3);
  });
});
