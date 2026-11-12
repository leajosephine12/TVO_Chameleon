import type { AnalysisGateway, ReviewRepository } from '../application/ports';
import type { ReviewedPage, ReviewVersion, Suggestion } from '../domain/review';
import { indexBlocks, normalizeHtml } from './pageBlocks';
import {
  isPageWide,
  suggestionsFromGeneralRecommendations,
  suggestionsFromRecommendations,
} from './recommendationSuggestions';

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
}

const notRun = (error: unknown): Found => ({
  suggestions: [],
  note: `The analysis could not be run: ${error instanceof Error ? error.message : 'unknown error'}`,
});

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

  async function dyslexiaSuggestions(page: ReviewedPage, html: string): Promise<Found> {
    const { recommendations } = await analysis.analyze(html);

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
      (s) => ({ ...s, id: `${page.url}#${s.id}` }),
    );
    return { suggestions, note: '' };
  }

  async function generalSuggestions(page: ReviewedPage, html: string, htmlUrl: string): Promise<Found> {
    const absoluteUrl = new URL(htmlUrl, window.location.origin).href;
    const { recommendations, modelError, layoutError } = await analysis.analyzeGeneral(html, absoluteUrl);

    // Both analyses number from "r1", so the version is part of the id: a decision on one never marks the other.
    const suggestions = suggestionsFromGeneralRecommendations(recommendations, indexBlocks(html)).map(
      (s) => ({ ...s, id: `${page.url}#${GENERAL_VERSION_ID}-${s.id}` }),
    );
    const notes = [
      modelError &&
        `The language model step failed (${modelError}), so only the measured layout fixes are shown.`,
      layoutError &&
        `Text size, line spacing and line length were not checked, because the backend could not open the page (${layoutError}).`,
    ];
    return { suggestions, note: notes.filter(Boolean).join(' ') };
  }

  /** Runs both analyses on the same HTML. One failing leaves the other version's suggestions in place. */
  async function analysePage(page: ReviewedPage) {
    const pageHtml = await fetchText(page.url);
    const targetFrame = findLessonFrame(pageHtml);
    const htmlUrl = targetFrame ? folderOf(page.url) + targetFrame : page.url;
    // Both the backend and indexBlocks count tags in this exact string, so their block ids always agree.
    const html = normalizeHtml(targetFrame ? await fetchText(htmlUrl) : pageHtml);

    const [general, dyslexia] = await Promise.all([
      generalSuggestions(page, html, htmlUrl).catch(notRun),
      dyslexiaSuggestions(page, html).catch(notRun),
    ]);
    return { targetFrame, found: { [GENERAL_VERSION_ID]: general, [DYSLEXIA_VERSION_ID]: dyslexia } };
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

      const blankVersions = base.versions.map((v) => ({ ...v, suggestions: [] }));
      try {
        const { targetFrame, found } = await analysePage(page);
        return { ...base, targetFrame, versions: withAnalysis(blankVersions, found) };
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
