/** Review rules. No React, DOM or storage here, so this layer can be reused and tested on its own. */

export type ReviewStatus = 'open' | 'approved' | 'rejected';
export type Category = 'cognitive' | 'wcag' | 'reading';
export type Priority = 'high' | 'medium' | 'low';
export type WcagCheck = 'pass' | 'fail' | 'review';

/** How a suggestion changes the page once it is approved. */
export type Patch =
  | { kind: 'css'; css: string }
  | { kind: 'insert'; selector: string; position: 'before' | 'after' | 'prepend' | 'append'; html: string }
  | { kind: 'replaceText'; selector: string; find: string; text: string }
  /** Swaps the element for the given HTML. Empty HTML removes the element and keeps what was inside it, if any. */
  | { kind: 'replaceElement'; selector: string; html: string }
  /** Sets the element's inline style. An empty style removes it. */
  | { kind: 'setStyle'; selector: string; style: string };

export interface Suggestion {
  id: string;
  title: string;
  /** The part of the page it applies to, such as "Sidebar activity list". */
  location: string;
  /** The text of the part it changes, so suggestions of the same kind can be told apart. Missing for the whole page. */
  excerpt?: string;
  summary: string;
  category: Category;
  priority: Priority;
  /** Null when no WCAG check was reported for it. */
  wcagCheck: WcagCheck | null;
  /** Where the finding comes from, such as a tool or a guideline. */
  evidence?: string;
  whatWouldChange: string;
  before: string;
  after: string;
  /** The elements to outline in the preview (a selector may match several), or null for the whole page. */
  targetSelector: string | null;
  /** The lesson tab the suggestion is in. Null or missing when it applies to the whole page or the page has no tabs. */
  tabId?: string | null;
  patches: Patch[];
}

/** A tab of a lesson, such as "Minds On". Only one tab's content is visible at a time. */
export interface LessonTab {
  id: string;
  label: string;
}

/** The id of the group that holds the suggestions that are not in any one tab. */
export const WHOLE_PAGE_GROUP_ID = 'whole-page';

/** A set of suggestions the reviewer looks at together: one lesson tab, or the whole page. */
export interface SuggestionGroup {
  id: string;
  label: string;
  count: number;
}

export interface ReviewVersion {
  id: string;
  name: string;
  /** Lower-case name used in running text, such as "general". */
  shortName: string;
  note: string;
  /** Visitors of this version also get what was approved for this other version. */
  builtOnVersionId?: string;
  suggestions: Suggestion[];
}

export interface ReviewedPage {
  label: string;
  url: string;
}

export type Decisions = Record<string, ReviewStatus>;

export interface ReviewSession {
  /** The `src` of the frame inside the page that the suggestions apply to, or null when they apply to the page itself. */
  targetFrame: string | null;
  /** The tabs of the lesson in the order it shows them. Empty when the page has no tabs. */
  lessonTabs: LessonTab[];
  versions: ReviewVersion[];
  decisions: Decisions;
}

const PRIORITY_ORDER: Priority[] = ['high', 'medium', 'low'];

export function statusOf(decisions: Decisions, suggestionId: string): ReviewStatus {
  return decisions[suggestionId] ?? 'open';
}

export function rankSuggestions(suggestions: Suggestion[]): Suggestion[] {
  return [...suggestions].sort(
    (a, b) => PRIORITY_ORDER.indexOf(a.priority) - PRIORITY_ORDER.indexOf(b.priority),
  );
}

export function countByStatus(suggestions: Suggestion[], decisions: Decisions): Record<ReviewStatus, number> {
  const counts: Record<ReviewStatus, number> = { open: 0, approved: 0, rejected: 0 };
  suggestions.forEach((s) => counts[statusOf(decisions, s.id)]++);
  return counts;
}

/** Everything a visitor of this version gets: its base version's approved items first, then its own. */
export function appliedSuggestions(session: ReviewSession, versionId: string): Suggestion[] {
  const version = session.versions.find((v) => v.id === versionId);
  if (!version) return [];
  const inherited = version.builtOnVersionId ? appliedSuggestions(session, version.builtOnVersionId) : [];
  const own = version.suggestions.filter((s) => statusOf(session.decisions, s.id) === 'approved');
  return [...inherited, ...own];
}

/** The tabs of a TVO Learn learning activity. Only a lesson that has all three is split by tab. */
const STANDARD_TAB_LABELS = ['minds on', 'action', 'consolidation'];

/**
 * The lesson tabs to split suggestions by: Minds On, Action and Consolidation, in the lesson's order.
 * A lesson that does not have all three gets no tabs, so its suggestions stay in one list.
 */
export function standardLessonTabs(lessonTabs: LessonTab[]): LessonTab[] {
  const standard = lessonTabs.filter((tab) => STANDARD_TAB_LABELS.includes(tab.label.toLowerCase()));
  return standard.length === STANDARD_TAB_LABELS.length ? standard : [];
}

/**
 * Splits suggestions by lesson tab, so the reviewer works through one tab at a time instead of one long
 * list. The group for the whole page comes first. Returns no groups when there are no lesson tabs,
 * because then there is nothing to split.
 */
export function groupSuggestions(lessonTabs: LessonTab[], suggestions: Suggestion[]): SuggestionGroup[] {
  if (lessonTabs.length === 0) return [];
  const countIn = (groupId: string) => suggestions.filter((s) => groupIdOf(s) === groupId).length;
  const groups = lessonTabs.map((tab) => ({ id: tab.id, label: tab.label, count: countIn(tab.id) }));
  const wholePageCount = countIn(WHOLE_PAGE_GROUP_ID);
  return wholePageCount > 0
    ? [{ id: WHOLE_PAGE_GROUP_ID, label: 'Whole page', count: wholePageCount }, ...groups]
    : groups;
}

/** The group a suggestion belongs to. */
export const groupIdOf = (suggestion: Suggestion): string => suggestion.tabId ?? WHOLE_PAGE_GROUP_ID;

/** The suggestions of one group. With no groups (a lesson without tabs), every suggestion is shown. */
export function suggestionsInGroup(
  suggestions: Suggestion[],
  groups: SuggestionGroup[],
  groupId: string,
): Suggestion[] {
  return groups.length === 0 ? suggestions : suggestions.filter((s) => groupIdOf(s) === groupId);
}
