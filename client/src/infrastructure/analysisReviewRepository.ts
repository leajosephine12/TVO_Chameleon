import type { AnalysisGateway, ReviewRepository } from '../application/ports';
import type { Recommendation } from '../domain/analysis';
import { standardLessonTabs, type ReviewedPage, type ReviewVersion, type Suggestion } from '../domain/review';
import { indexBlocks, normalizeHtml, readLessonTabs } from './pageBlocks';
import {
  isPageWide,
  stableRecommendationIds,
  suggestionsFromGeneralRecommendations,
  suggestionsFromRecommendations,
} from './recommendationSuggestions';

/**
 * What reviewers read when part of the analysis is missing. The technical reason (an unset model name, a
 * refused connection) means nothing to a reviewer, so it goes to the browser console for developers instead.
 */
export const MODEL_UNAVAILABLE_NOTE =
  'Wording suggestions are missing because the language model could not be reached. Only the measured layout fixes are shown.';
export const LAYOUT_UNCHECKED_NOTE =
  'Text size, line spacing and line length were not checked, because the backend could not open the page.';
export const ANALYSIS_UNAVAILABLE_NOTE =
  'Suggestions could not be loaded for this page because the analysis service did not answer. You can still view the page.';

/** What the backend is given to build a page-wide rule's CSS. That CSS does not depend on the page. */
const STUB_PAGE = '<html><head></head><body><p>Text</p></body></html>';

/**
 * The backend analyses a page twice, once for each version, and the two results are never mixed:
 * POST /analyze_general fills the general version and POST /analyze (dyslexia rules) fills the dyslexia one.
 */
const GENERAL_VERSION_ID = 'general';
const DYSLEXIA_VERSION_ID = 'dyslexia';

/** What one of the two analyses found for its version, or the reason there is nothing. */
interface Found {
  suggestions: Suggestion[];
  note: string;
  /** True when the analysis could not be run at all, so the next visit to the page should try again. */
  failed?: boolean;
}

const notRun = (error: unknown): Found => {
  console.warn('The analysis could not be run:', error);
  return { suggestions: [], note: ANALYSIS_UNAVAILABLE_NOTE, failed: true };
};

/** What a page's suggestions need besides the change itself: the page they are on and its lesson tabs. */
interface Placement {
  pageUrl: string;
  knownTabIds: Set<string>;
}

/**
 * Gives each suggestion its final id and lesson tab.
 *
 * Decisions are kept for all pages together and must survive a new analysis of the same page, so each id is
 * the page plus an id built from what the recommendation is (see stableRecommendationIds). `idPrefix` keeps
 * the two analyses apart, so a decision on one version never marks a suggestion of the other.
 * A block in a panel with no tab link has no tab to show it under, so it counts as whole-page.
 */
function placed(
  suggestions: Suggestion[],
  recommendations: Recommendation[],
  { pageUrl, knownTabIds }: Placement,
  idPrefix = '',
): Suggestion[] {
  const stableIds = stableRecommendationIds(recommendations);
  return suggestions.map((s) => ({
    ...s,
    id: `${pageUrl}#${idPrefix}${stableIds.get(s.id) ?? s.id}`,
    tabId: s.tabId && knownTabIds.has(s.tabId) ? s.tabId : null,
  }));
}

const fetchText = async (url: string): Promise<string> => {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`The page could not be loaded (${response.status}).`);
  return response.text();
};

/**
 * The `src` of the frame that holds a captured lesson, such as "frames/f0.html", or null if the page has none.
 * The capture tool copies embedded lessons next to the page, and the lesson is what the backend should read.
 */
export function findLessonFrame(pageHtml: string): string | null {
  const frame = new DOMParser()
    .parseFromString(pageHtml, 'text/html')
    .querySelector('iframe[src^="frames/"]');
  return frame?.getAttribute('src') ?? null;
}

/**
 * Builds the review of a captured page from what the analysis backend finds in it.
 * Pages without an analysis (the sample page) and decisions come from `fallback`.
 */
export function createAnalysisReviewRepository(
  fallback: ReviewRepository,
  analysis: AnalysisGateway,
  samplePage: ReviewedPage,
): ReviewRepository {
  /** Splits a page URL into the folder it is in, so a frame's relative `src` can be loaded. */
  const folderOf = (pageUrl: string) => pageUrl.slice(0, pageUrl.lastIndexOf('/') + 1);

  async function dyslexiaSuggestions(html: string, placement: Placement): Promise<Found> {
    const { recommendations } = await analysis.analyze(html);

    // Page-wide rules are previewed with the CSS the backend would inject for each of them.
    const pageCss: Record<string, string> = {};
    await Promise.all(
      recommendations.filter(isPageWide).map(async (rec) => {
        const adaptation = await analysis.adapt(STUB_PAGE, [{ ...rec, status: 'accepted' }]);
        pageCss[rec.id] = adaptation.injectedCss;
      }),
    );

    const suggestions = suggestionsFromRecommendations(recommendations, indexBlocks(html), pageCss);
    return { suggestions: placed(suggestions, recommendations, placement), note: '' };
  }

  async function generalSuggestions(html: string, htmlUrl: string, placement: Placement): Promise<Found> {
    const absoluteUrl = new URL(htmlUrl, window.location.origin).href;
    const { recommendations, modelError, layoutError } = await analysis.analyzeGeneral(html, absoluteUrl);

    const suggestions = suggestionsFromGeneralRecommendations(recommendations, indexBlocks(html));
    if (modelError) console.warn(`Language model step failed: ${modelError}`);
    if (layoutError) console.warn(`Layout check could not open the page: ${layoutError}`);
    const notes = [modelError && MODEL_UNAVAILABLE_NOTE, layoutError && LAYOUT_UNCHECKED_NOTE];
    return {
      suggestions: placed(suggestions, recommendations, placement, `${GENERAL_VERSION_ID}-`),
      note: notes.filter(Boolean).join(' '),
    };
  }

  /**
   * What each analysis found for each page, kept for as long as the app is open. The language model can take
   * minutes, so going back to a page that was already analysed must not run it again. An analysis that could
   * not be run (the backend was down) is not kept, so the next visit tries that one again; the other
   * version's result stays, with the ids its decisions were saved under.
   */
  const results = new Map<string, Promise<Found>>();
  function once(key: string, run: () => Promise<Found>): Promise<Found> {
    let result = results.get(key);
    if (!result) {
      result = run().catch(notRun);
      results.set(key, result);
      void result.then((found) => found.failed && results.delete(key));
    }
    return result;
  }

  /** Runs both analyses on the same HTML. One failing leaves the other version's suggestions in place. */
  async function analysePage(page: ReviewedPage) {
    const pageHtml = await fetchText(page.url);
    const targetFrame = findLessonFrame(pageHtml);
    const htmlUrl = targetFrame ? folderOf(page.url) + targetFrame : page.url;
    // Both the backend and indexBlocks count tags in this exact string, so their block ids always agree.
    const html = normalizeHtml(targetFrame ? await fetchText(htmlUrl) : pageHtml);

    const lessonTabs = standardLessonTabs(readLessonTabs(html));
    const placement = { pageUrl: page.url, knownTabIds: new Set(lessonTabs.map((tab) => tab.id)) };
    const [general, dyslexia] = await Promise.all([
      once(`${page.url}#${GENERAL_VERSION_ID}`, () => generalSuggestions(html, htmlUrl, placement)),
      once(`${page.url}#${DYSLEXIA_VERSION_ID}`, () => dyslexiaSuggestions(html, placement)),
    ]);
    return {
      targetFrame,
      lessonTabs,
      found: { [GENERAL_VERSION_ID]: general, [DYSLEXIA_VERSION_ID]: dyslexia } as Record<string, Found>,
    };
  }

  /** Puts what each analysis found (or why there is nothing) into its own version. */
  const withAnalysis = (versions: ReviewVersion[], found: Record<string, Found>) =>
    versions.map((v) =>
      found[v.id]
        ? { ...v, suggestions: found[v.id].suggestions, note: `${v.note} ${found[v.id].note}`.trim() }
        : v,
    );

  return {
    loadSession: async (page) => {
      const base = await fallback.loadSession(page);
      if (page.url === samplePage.url) return base;

      const blankVersions = base.versions.map((v) => ({
        ...v,
        suggestions: [],
      }));
      try {
        const { targetFrame, lessonTabs, found } = await analysePage(page);
        return { ...base, targetFrame, lessonTabs, versions: withAnalysis(blankVersions, found) };
      } catch (error) {
        // Without the captured page there is nothing to analyse, so say what is missing instead of failing.
        const failed = notRun(error);
        return {
          ...base,
          versions: withAnalysis(blankVersions, {
            [GENERAL_VERSION_ID]: failed,
            [DYSLEXIA_VERSION_ID]: failed,
          }),
        };
      }
    },
    saveDecision: fallback.saveDecision,
  };
}
