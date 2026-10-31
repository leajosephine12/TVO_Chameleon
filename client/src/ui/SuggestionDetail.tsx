import type { ReviewStatus, Suggestion } from '../domain/review';
import { PRIORITY_LABEL, WCAG_CHECK_LABEL } from './labels';

interface Props {
  suggestion: Suggestion;
  position: number;
  total: number;
  status: ReviewStatus;
  onDecide: (status: ReviewStatus) => void;
  onPrevious: () => void;
  onNext: () => void;
}

export function SuggestionDetail({
  suggestion,
  position,
  total,
  status,
  onDecide,
  onPrevious,
  onNext,
}: Props) {
  // Pressing the current decision again takes it back.
  const toggle = (next: ReviewStatus) => onDecide(status === next ? 'open' : next);

  return (
    <article className="suggestion-detail" aria-labelledby="suggestion-title">
      <p className="eyebrow">
        <span>
          Suggestion {position} of {total}
        </span>{' '}
        · {suggestion.location}
      </p>
      <h2 id="suggestion-title">{suggestion.title}</h2>
      <p>{suggestion.summary}</p>
      <div className="chips">
        <span className={`chip chip-${suggestion.wcagCheck}`}>{WCAG_CHECK_LABEL[suggestion.wcagCheck]}</span>
        <span className="chip">
          <i className={`priority-bar priority-${suggestion.priority}`} aria-hidden="true" />
          {PRIORITY_LABEL[suggestion.priority]} priority
        </span>
      </div>
      <div className="decision">
        <button
          type="button"
          className="decide approve"
          aria-pressed={status === 'approved'}
          onClick={() => toggle('approved')}
        >
          Approve
        </button>
        <button
          type="button"
          className="decide reject"
          aria-pressed={status === 'rejected'}
          onClick={() => toggle('rejected')}
        >
          Reject
        </button>
        <button type="button" className="step" aria-label="Previous suggestion" onClick={onPrevious}>
          ‹
        </button>
        <button type="button" className="step" aria-label="Next suggestion" onClick={onNext}>
          ›
        </button>
      </div>
      <h3 className="eyebrow">What would change</h3>
      <p className="what-changes">{suggestion.whatWouldChange}</p>
      <div className="comparison">
        <div>
          <h4>Now</h4>
          <p>{suggestion.before}</p>
        </div>
        <div>
          <h4>With this change</h4>
          <p>{suggestion.after}</p>
        </div>
      </div>
    </article>
  );
}
