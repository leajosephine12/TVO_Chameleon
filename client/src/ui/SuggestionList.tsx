import { useEffect, useRef, type ReactNode } from 'react';
import { statusOf, type Decisions, type Suggestion } from '../domain/review';
import { PRIORITY_LABEL, STATUS_LABEL } from './labels';

interface Props {
  suggestions: Suggestion[];
  decisions: Decisions;
  /** The row that is open, or null when all rows are closed. */
  selectedId: string | null;
  /** Called with null when the open row is clicked again, to close it. */
  onSelect: (id: string | null) => void;
  /** What to show under the selected row. */
  renderDetail: (suggestion: Suggestion) => ReactNode;
}

/**
 * Where a suggestion applies, as the row shows it: a quote of the text it changes when there is one, since
 * many rows share a title such as "Italic text"; otherwise where on the page it is.
 */
function whereOf(suggestion: Suggestion): string {
  return suggestion.excerpt ? `“${suggestion.excerpt}”` : suggestion.location;
}

/**
 * The suggestions as numbered rows. Each row shows what the suggestion is, where it applies, how important
 * it is and whether it was decided; the open row has its details underneath.
 */
export function SuggestionList({ suggestions, decisions, selectedId, onSelect, renderDetail }: Props) {
  const listRef = useRef<HTMLOListElement>(null);

  // Opening a row closes the one above it, which can leave the new row out of view, so bring it back.
  useEffect(() => {
    listRef.current?.querySelector('[aria-current]')?.scrollIntoView?.({ block: 'nearest' });
  }, [selectedId]);

  return (
    <ol ref={listRef} className="suggestion-list">
      {suggestions.map((suggestion, index) => {
        const status = statusOf(decisions, suggestion.id);
        const isSelected = suggestion.id === selectedId;
        return (
          <li key={suggestion.id}>
            <button
              type="button"
              className="suggestion-row"
              aria-current={isSelected ? 'true' : undefined}
              aria-expanded={isSelected}
              onClick={() => onSelect(isSelected ? null : suggestion.id)}
            >
              <span className="rank" aria-hidden="true">
                {index + 1}
              </span>
              <span className="suggestion-row-text">
                <strong>{suggestion.title}</strong>
                <small>
                  <span className="row-where">{whereOf(suggestion)}</span>
                  <span className="row-priority">{PRIORITY_LABEL[suggestion.priority]} priority</span>
                </small>
              </span>
              <span className={`status status-${status}`}>{STATUS_LABEL[status]}</span>
            </button>
            {isSelected && renderDetail(suggestion)}
          </li>
        );
      })}
    </ol>
  );
}
