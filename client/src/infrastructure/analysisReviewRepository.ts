import type { AnalysisGateway, ReviewRepository } from '../application/ports';
import { standardLessonTabs, type ReviewedPage, type ReviewVersion, type Suggestion } from '../domain/review';
import { indexBlocks, normalizeHtml, readLessonTabs } from './pageBlocks';
import {
  isPageWide,
  stableRecommendationIds,
  suggestionsFromRecommendations,
} from './recommendationSuggestions';

/** What the backend is given to build a page-wide rule's CSS. That CSS does not depend on the page. */
const STUB_PAGE = '<html><head></head><body><p>Text</p></body></html>';

/** The version the backend's recommendations belong to. The other versions have no analysis yet. */
const ANALYSED_VERSION_ID = 'dyslexia';

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

  async function analysePage(page: ReviewedPage) {
    const pageHtml = await fetchText(page.url);
    const targetFrame = findLessonFrame(pageHtml);
    // Both the backend and indexBlocks count tags in this exact string, so their block ids always agree.
    const html = normalizeHtml(targetFrame ? await fetchText(folderOf(page.url) + targetFrame) : pageHtml);

    const { recommendations, modelError } = await analysis.analyze(html);

    // Page-wide rules are previewed with the CSS the backend would inject for each of them.
    const pageCss: Record<string, string> = {};
    await Promise.all(
      recommendations.filter(isPageWide).map(async (rec) => {
        const adaptation = await analysis.adapt(STUB_PAGE, [{ ...rec, status: 'accepted' }]);
        pageCss[rec.id] = adaptation.injectedCss;
      }),
    );

    const lessonTabs = standardLessonTabs(readLessonTabs(html));
    const knownTabIds = new Set(lessonTabs.map((tab) => tab.id));

    // Decisions are kept for all pages together and must survive a new analysis of the same page, so each
    // id is the page plus an id built from what the recommendation is (see stableRecommendationIds).
    const stableIds = stableRecommendationIds(recommendations);
    // A block in a panel with no tab link has no tab to show it under, so it counts as whole-page.
    const suggestions = suggestionsFromRecommendations(recommendations, indexBlocks(html), pageCss).map(
      (s) => ({
        ...s,
        id: `${page.url}#${stableIds.get(s.id) ?? s.id}`,
        tabId: s.tabId && knownTabIds.has(s.tabId) ? s.tabId : null,
      }),
    );
    return { targetFrame, lessonTabs, suggestions, modelError };
  }

  /**
   * What the analysis found for each page, kept for as long as the app is open. The language model can take
   * minutes, so going back to a page that was already analysed must not run it again.
   */
  const analyses = new Map<string, ReturnType<typeof analysePage>>();
  function analysisOf(page: ReviewedPage) {
    let analysis = analyses.get(page.url);
    if (!analysis) {
      analysis = analysePage(page);
      analyses.set(page.url, analysis);
      // A failed analysis (the backend was down) is not kept, so the next visit tries again.
      analysis.catch(() => analyses.delete(page.url));
    }
    return analysis;
  }

  /** Puts what the analysis found (or why there is none) into the version the backend analyses for. */
  const withAnalysis = (versions: ReviewVersion[], suggestions: Suggestion[], note: string) =>
    versions.map((v) =>
      v.id === ANALYSED_VERSION_ID ? { ...v, suggestions, note: `${v.note} ${note}`.trim() } : v,
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
        const { targetFrame, lessonTabs, suggestions, modelError } = await analysisOf(page);
        const note = modelError
          ? `The language model step failed (${modelError}), so only the rule-based findings are shown.`
          : '';
        return {
          ...base,
          targetFrame,
          lessonTabs,
          versions: withAnalysis(blankVersions, suggestions, note),
        };
      } catch (error) {
        // Without the backend the page can still be looked at, so say what is missing instead of failing.
        const reason = error instanceof Error ? error.message : 'unknown error';
        return {
          ...base,
          versions: withAnalysis(blankVersions, [], `The analysis could not be run: ${reason}`),
        };
      }
    },
    saveDecision: fallback.saveDecision,
  };
}
