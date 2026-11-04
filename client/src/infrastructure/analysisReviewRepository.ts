import type { AnalysisGateway, ReviewRepository } from '../application/ports';
import type { ReviewedPage, ReviewVersion, Suggestion } from '../domain/review';
import { indexBlocks } from './pageBlocks';
import { isPageWide, suggestionsFromRecommendations } from './recommendationSuggestions';

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
    // The same HTML must go to the backend and to indexBlocks, or block ids point at the wrong elements.
    const html = targetFrame ? await fetchText(folderOf(page.url) + targetFrame) : pageHtml;

    const { recommendations, modelError } = await analysis.analyze(html);

    // Page-wide rules are previewed with the CSS the backend would inject for each of them.
    const pageCss: Record<string, string> = {};
    await Promise.all(
      recommendations.filter(isPageWide).map(async (rec) => {
        const adaptation = await analysis.adapt(STUB_PAGE, [{ ...rec, status: 'accepted' }]);
        pageCss[rec.id] = adaptation.injectedCss;
      }),
    );

    // Ids are only unique within one analysis, and decisions are kept for all pages together.
    const suggestions = suggestionsFromRecommendations(recommendations, indexBlocks(html), pageCss).map(
      (s) => ({
        ...s,
        id: `${page.url}#${s.id}`,
      }),
    );
    return { targetFrame, suggestions, modelError };
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

      const blankVersions = base.versions.map((v) => ({ ...v, suggestions: [] }));
      try {
        const { targetFrame, suggestions, modelError } = await analysePage(page);
        const note = modelError
          ? `The language model could not be reached (${modelError}), so only the rule-based findings are shown.`
          : '';
        return { ...base, targetFrame, versions: withAnalysis(blankVersions, suggestions, note) };
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
