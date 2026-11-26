import type { ReviewStatus, Suggestion } from '../domain/review';
import { changePreview } from './changePreview';
import { CATEGORY_LABEL, PRIORITY_LABEL, WCAG_CHECK_LABEL } from './labels';

interface Props {
  suggestion: Suggestion;
  status: ReviewStatus;
  onDecide: (status: ReviewStatus) => void;
  /** Open the suggestion above or below this one in the list. */
  onPrevious: () => void;
  onNext: () => void;
}

/** One side of the comparison: the words as a reader sees them, with the italics, bold or underline they have. */
function ChangeSide({ label, side, tone }: { label: string; side: string; tone: 'now' | 'after' }) {
  const { text, emphasis, isCode } = changePreview(side);
  const textClass = isCode
    ? 'change-text change-code'
    : `change-text${emphasis ? ` emphasis-${emphasis}` : ''}`;
  return (
    <div className={`change-side change-${tone}`}>
      <h4>{label}</h4>
      <p className={textClass}>{text || '(removed)'}</p>
    </div>
  );
}

/** The full suggestion, shown directly under its row in the list. The row above already names it. */
export function SuggestionDetail({ suggestion, status, onDecide, onPrevious, onNext }: Props) {
  // Pressing the current decision again takes it back.
  const toggle = (next: ReviewStatus) => onDecide(status === next ? 'open' : next);

  return (
    <article className="suggestion-detail" aria-label={`Details: ${suggestion.title}`}>
      <p className="detail-summary">{suggestion.summary}</p>

      <div className="comparison">
        <ChangeSide label="Now" side={suggestion.before} tone="now" />
        <ChangeSide label="After" side={suggestion.after} tone="after" />
      </div>

      <div className="chips">
        <span className="chip">
          <i className={`dot dot-${suggestion.category}`} aria-hidden="true" />
          {CATEGORY_LABEL[suggestion.category]}
        </span>
        <span className="chip">{PRIORITY_LABEL[suggestion.priority]} priority</span>
        {suggestion.wcagCheck && (
          <span className={`chip chip-${suggestion.wcagCheck}`}>
            {WCAG_CHECK_LABEL[suggestion.wcagCheck]}
          </span>
        )}
      </div>
      {suggestion.evidence && <p className="evidence">Source: {suggestion.evidence}</p>}

      <div className="decision">
        <button
          type="button"
          className="decide approve"
          aria-pressed={status === 'approved'}
          onClick={() => toggle('approved')}
        >
          {status === 'approved' ? 'Approved' : 'Approve'}
        </button>
        <button
          type="button"
          className="decide reject"
          aria-pressed={status === 'rejected'}
          onClick={() => toggle('rejected')}
        >
          {status === 'rejected' ? 'Rejected' : 'Reject'}
        </button>
        <button type="button" className="step" aria-label="Previous suggestion" onClick={onPrevious}>
          <svg
            aria-hidden="true"
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="m15 18-6-6 6-6" />
          </svg>
        </button>
        <button type="button" className="step" aria-label="Next suggestion" onClick={onNext}>
          <svg
            aria-hidden="true"
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="m9 18 6-6-6-6" />
          </svg>
        </button>
      </div>
    </article>
  );
}
