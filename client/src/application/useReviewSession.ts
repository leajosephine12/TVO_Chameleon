import { useCallback, useEffect, useState } from 'react';
import type { ReviewedPage, ReviewSession, ReviewStatus } from '../domain/review';
import type { ReviewRepository } from './ports';

/** Loads the review of a page and records decisions, undoing a decision that could not be saved. */
export function useReviewSession(repository: ReviewRepository, page: ReviewedPage) {
  const [session, setSession] = useState<ReviewSession | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    repository
      .loadSession(page)
      .then((loaded) => {
        if (!cancelled) setSession(loaded);
      })
      .catch(() => {
        if (!cancelled) setError('The review could not be loaded.');
      });
    return () => {
      cancelled = true;
    };
  }, [repository, page]);

  const decide = useCallback(
    (suggestionId: string, status: ReviewStatus) => {
      const setStatus = (next: ReviewStatus | undefined) =>
        setSession((s) => s && { ...s, decisions: { ...s.decisions, [suggestionId]: next ?? 'open' } });
      const previous = session?.decisions[suggestionId];
      setError(null);
      setStatus(status);
      repository.saveDecision(suggestionId, status).catch(() => {
        setStatus(previous);
        setError('That decision could not be saved. Try again.');
      });
    },
    [repository, session],
  );

  return { session, error, decide };
}
