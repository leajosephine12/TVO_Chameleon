import type { ReviewRepository } from '../application/ports';
import type { Decisions, ReviewedPage, ReviewVersion } from '../domain/review';

const STORAGE_KEY = 'tvo-chameleon:decisions';

function readDecisions(): Decisions {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}') as Decisions;
  } catch {
    return {};
  }
}

/**
 * Stands in until there is a server. Only the sample page has suggestions, because patches are written
 * for one specific page. Decisions are kept in this browser.
 */
export function createLocalReviewRepository(
  samplePage: ReviewedPage,
  sampleVersions: ReviewVersion[],
): ReviewRepository {
  return {
    loadSession: async (page) => ({
      versions:
        page.url === samplePage.url
          ? sampleVersions
          : sampleVersions.map((version) => ({ ...version, suggestions: [] })),
      decisions: readDecisions(),
    }),
    saveDecision: async (suggestionId, status) => {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...readDecisions(), [suggestionId]: status }));
      } catch {
        // Storage can be blocked. The decision still holds until the page is reloaded.
      }
    },
  };
}
