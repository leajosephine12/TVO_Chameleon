import type { KeyboardEvent } from 'react';
import {
  countByStatus,
  rankSuggestions,
  statusOf,
  suggestionsInGroup,
  type ReviewSession,
  type ReviewStatus,
  type ReviewVersion,
  type SuggestionGroup,
} from '../domain/review';
import { capitalize } from './labels';
import { SuggestionDetail } from './SuggestionDetail';
import { SuggestionList } from './SuggestionList';
import { useSlidingHighlight } from './useSlidingHighlight';

interface Props {
  session: ReviewSession;
  version: ReviewVersion;
  /** The suggestion that is open, or null when all of them are closed. */
  selectedId: string | null;
  /** The lesson tabs (and whole page) the suggestions are split into. Empty when there is nothing to split. */
  groups: SuggestionGroup[];
  activeGroupId: string;
  /** True while this page's analysis is running. `session` still holds the previous page's review then. */
  isLoading: boolean;
  error: string | null;
  onGroupChange: (groupId: string) => void;
  onVersionChange: (versionId: string) => void;
  onSelect: (suggestionId: string | null) => void;
  onDecide: (suggestionId: string, status: ReviewStatus) => void;
  onSeeVisitorView: () => void;
}

export function ReviewPanel({
  session,
  version,
  selectedId,
  groups,
  activeGroupId,
  isLoading,
  error,
  onGroupChange,
  onVersionChange,
  onSelect,
  onDecide,
  onSeeVisitorView,
}: Props) {
  const { versions, decisions } = session;
  // The previous page's suggestions are not shown while this page's are being worked out.
  const allSuggestions = isLoading ? [] : version.suggestions;
  const counts = countByStatus(allSuggestions, decisions);
  // Progress is for the whole version; the footer below counts only the open tab.
  const versionCounts = countByStatus(allSuggestions, decisions);
  const reviewed = versionCounts.approved + versionCounts.rejected;
  const percentOf = (count: number) =>
    allSuggestions.length === 0 ? '0%' : `${(count / allSuggestions.length) * 100}%`;
  // The highlight slides under the chosen version, like the other switches in the app.
  const versionSwitch = useSlidingHighlight(versions.indexOf(version));
  // Only the suggestions of the open lesson tab are listed, so the list stays short.
  const suggestions = rankSuggestions(suggestionsInGroup(allSuggestions, groups, activeGroupId));
  const selected = suggestions.find((s) => s.id === selectedId);
  // Opens the suggestion `by` places from the open one, wrapping around at either end of the list.
  // With none open, forward opens the first and back opens the last.
  const step = (by: number) => {
    const index = selected ? suggestions.indexOf(selected) : by > 0 ? -1 : 0;
    onSelect(suggestions[(index + by + suggestions.length) % suggestions.length].id);
  };

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
      <div className="panel-header">
        <div
          className="version-switch"
          role="tablist"
          aria-label="Page version"
          onKeyDown={onTabKey}
          ref={versionSwitch.containerRef}
        >
          <span className="switch-highlight" aria-hidden="true" style={versionSwitch.highlightStyle} />
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
              {capitalize(v.shortName)}
              <span className="version-count">{isLoading ? 0 : v.suggestions.length}</span>
            </button>
          ))}
        </div>
        {/* While a page loads or has no suggestions, the message in the list says so; a 0 of 0 bar adds nothing. */}
        {allSuggestions.length > 0 && (
          <div className="review-progress">
            <div className="review-progress-text">
              <strong>
                {reviewed} of {allSuggestions.length} reviewed
              </strong>
              <span>
                {versionCounts.approved} approved · {versionCounts.rejected} rejected
              </span>
            </div>
            <div
              className="review-progress-bar"
              role="progressbar"
              aria-label="Suggestions reviewed"
              aria-valuemin={0}
              aria-valuemax={allSuggestions.length}
              aria-valuenow={reviewed}
            >
              <span className="bar-approved" style={{ width: percentOf(versionCounts.approved) }} />
              <span className="bar-rejected" style={{ width: percentOf(versionCounts.rejected) }} />
            </div>
          </div>
        )}
      </div>
      <div className="review-scroll" id="version-panel" role="tabpanel" aria-labelledby={`tab-${version.id}`}>
        <p className="version-note">{version.note}</p>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        {groups.length > 0 && !isLoading && (
          <div className="group-tabs" role="group" aria-label="Lesson tab">
            {groups.map((group) => (
              <button
                key={group.id}
                type="button"
                className="group-tab"
                aria-pressed={group.id === activeGroupId}
                onClick={() => onGroupChange(group.id)}
              >
                {group.label}
                <span className="group-count">{group.count}</span>
              </button>
            ))}
          </div>
        )}
        {isLoading ? (
          <p className="no-suggestions" role="status">
            Analysing this page. With the language model this can take a few minutes.
          </p>
        ) : suggestions.length === 0 ? (
          <p className="no-suggestions">
            {groups.length > 0
              ? 'No suggestions for this tab.'
              : 'No suggestions for this version of the page.'}
          </p>
        ) : (
          <SuggestionList
            suggestions={suggestions}
            decisions={decisions}
            selectedId={selected?.id ?? null}
            onSelect={onSelect}
            renderDetail={(suggestion) => (
              <SuggestionDetail
                suggestion={suggestion}
                status={statusOf(decisions, suggestion.id)}
                onDecide={(status) => onDecide(suggestion.id, status)}
                onPrevious={() => step(-1)}
                onNext={() => step(1)}
              />
            )}
          />
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
