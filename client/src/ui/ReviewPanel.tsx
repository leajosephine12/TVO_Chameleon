import type { KeyboardEvent } from 'react';
import {
  appliedSuggestions,
  countByStatus,
  rankSuggestions,
  statusOf,
  type ReviewSession,
  type ReviewStatus,
  type ReviewVersion,
} from '../domain/review';
import { capitalize } from './labels';
import { SuggestionDetail } from './SuggestionDetail';
import { SuggestionList } from './SuggestionList';

interface Props {
  session: ReviewSession;
  version: ReviewVersion;
  selectedId: string;
  error: string | null;
  onVersionChange: (versionId: string) => void;
  onSelect: (suggestionId: string) => void;
  onDecide: (suggestionId: string, status: ReviewStatus) => void;
  onSeeVisitorView: () => void;
}

export function ReviewPanel({
  session,
  version,
  selectedId,
  error,
  onVersionChange,
  onSelect,
  onDecide,
  onSeeVisitorView,
}: Props) {
  const { versions, decisions } = session;
  const suggestions = rankSuggestions(version.suggestions);
  const counts = countByStatus(suggestions, decisions);
  const applied = appliedSuggestions(session, version.id).length;
  const selectedIndex = Math.max(
    suggestions.findIndex((s) => s.id === selectedId),
    0,
  );
  const selected = suggestions[selectedIndex];
  const step = (by: number) =>
    onSelect(suggestions[(selectedIndex + by + suggestions.length) % suggestions.length].id);

  const onTabKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    const by = e.key === 'ArrowRight' ? 1 : -1;
    const index = versions.indexOf(version);
    const next = versions[(index + by + versions.length) % versions.length];
    onVersionChange(next.id);
    document.getElementById(`tab-${next.id}`)?.focus();
  };

  return (
    <section className="review-panel" aria-label="Review">
      <div className="version-tabs" role="tablist" aria-label="Page version" onKeyDown={onTabKey}>
        {versions.map((v) => (
          <button
            key={v.id}
            id={`tab-${v.id}`}
            type="button"
            role="tab"
            aria-selected={v.id === version.id}
            aria-controls="version-panel"
            tabIndex={v.id === version.id ? 0 : -1}
            onClick={() => onVersionChange(v.id)}
          >
            <strong>{v.name}</strong>
            <small>
              {countByStatus(v.suggestions, decisions).approved} of {v.suggestions.length} approved
            </small>
          </button>
        ))}
      </div>
      <div className="review-scroll" id="version-panel" role="tabpanel" aria-labelledby={`tab-${version.id}`}>
        <p className="version-note">{version.note}</p>
        <p className="applied" role="status">
          {capitalize(version.shortName)} version: {applied} approved {applied === 1 ? 'change' : 'changes'}{' '}
          applied.
        </p>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        {suggestions.length === 0 ? (
          <p className="no-suggestions">
            No suggestions for this page yet. They will appear here once the analysis backend provides them.
          </p>
        ) : (
          <>
            <SuggestionList
              suggestions={suggestions}
              decisions={decisions}
              selectedId={selected.id}
              onSelect={onSelect}
            />
            <SuggestionDetail
              suggestion={selected}
              position={selectedIndex + 1}
              total={suggestions.length}
              status={statusOf(decisions, selected.id)}
              onDecide={(status) => onDecide(selected.id, status)}
              onPrevious={() => step(-1)}
              onNext={() => step(1)}
            />
          </>
        )}
      </div>
      <footer className="review-footer">
        <span>
          Approved <b>{counts.approved}</b>
        </span>
        <span>
          Rejected <b>{counts.rejected}</b>
        </span>
        <span>
          Open <b>{counts.open}</b>
        </span>
        <button type="button" className="visitor-button" onClick={onSeeVisitorView}>
          See what visitors get
        </button>
      </footer>
    </section>
  );
}
