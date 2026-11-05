import { statusOf, type Decisions, type Suggestion } from '../domain/review';
import { CATEGORY_LABEL, PRIORITY_LABEL, STATUS_LABEL } from './labels';

interface Props {
  suggestions: Suggestion[];
  decisions: Decisions;
  selectedId: string;
  onSelect: (id: string) => void;
}

export function SuggestionList({ suggestions, decisions, selectedId, onSelect }: Props) {
  return (
    <ol className="suggestion-list">
      {suggestions.map((suggestion, index) => {
        const status = statusOf(decisions, suggestion.id);
        return (
          <li key={suggestion.id}>
            <button
              type="button"
              className="suggestion-row"
              aria-current={suggestion.id === selectedId ? 'true' : undefined}
              onClick={() => onSelect(suggestion.id)}
            >
              <span className="rank" aria-hidden="true">
                {index + 1}
              </span>
              <span className="suggestion-row-text">
                <strong>{suggestion.title}</strong>
                <small>
                  <i className={`dot dot-${suggestion.category}`} aria-hidden="true" />
                  {CATEGORY_LABEL[suggestion.category]}
                  <span>{PRIORITY_LABEL[suggestion.priority]}</span>
                </small>
              </span>
              <span className={`status status-${status}`}>{STATUS_LABEL[status]}</span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}
