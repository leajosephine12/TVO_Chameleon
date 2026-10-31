/** Review rules. No React, DOM or storage here, so this layer can be reused and tested on its own. */

export type ReviewStatus = 'open' | 'approved' | 'rejected';
export type Category = 'cognitive' | 'wcag' | 'reading';
export type Priority = 'high' | 'medium' | 'low';
export type WcagCheck = 'pass' | 'fail' | 'review';

/** How a suggestion changes the page once it is approved. */
export type Patch =
  | { kind: 'css'; css: string }
  | { kind: 'insert'; selector: string; position: 'before' | 'after' | 'prepend' | 'append'; html: string }
  | { kind: 'replaceText'; selector: string; find: string; text: string };

export interface Suggestion {
  id: string;
  title: string;
  /** The part of the page it applies to, such as "Sidebar activity list". */
  location: string;
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
  /** The element to point at in the preview. */
  targetSelector: string;
  patches: Patch[];
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
