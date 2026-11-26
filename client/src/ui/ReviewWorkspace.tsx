import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { CaptureGateway, ReviewRepository } from '../application/ports';
import { useCaptures } from '../application/useCaptures';
import { useReviewSession } from '../application/useReviewSession';
import { pageFromCapture, type PageCapture } from '../domain/capture';
import {
  appliedSuggestions,
  groupSuggestions,
  suggestionsInGroup,
  type ReviewedPage,
} from '../domain/review';
import { AppHeader, type ViewAs } from './AppHeader';
import { CaptureBar } from './CaptureBar';
import { capitalize } from './labels';
import { PagePreview } from './PagePreview';
import { ReviewPanel } from './ReviewPanel';
import { SegmentedControl } from './SegmentedControl';

type PreviewMode = 'approved' | 'original';

interface Props {
  repository: ReviewRepository;
  captureGateway: CaptureGateway;
  samplePage: ReviewedPage;
}

export function ReviewWorkspace({ repository, captureGateway, samplePage }: Props) {
  const [page, setPage] = useState(samplePage);
  const { session, error, decide, isLoading } = useReviewSession(repository, page);

  // A capture takes minutes. The new page opens by itself only if the reviewer is still on the page they
  // started it from; if they moved on, it waits for them to open it, so their review is not taken away.
  const currentPageUrl = useRef(page.url);
  useEffect(() => {
    currentPageUrl.current = page.url;
  }, [page.url]);
  const pageUrlWhenCaptureStarted = useRef<string | null>(null);
  const [capturedPageToOpen, setCapturedPageToOpen] = useState<ReviewedPage | null>(null);
  const onCaptured = useCallback((capture: PageCapture) => {
    const captured = pageFromCapture(capture);
    if (currentPageUrl.current === pageUrlWhenCaptureStarted.current) setPage(captured);
    else setCapturedPageToOpen(captured);
  }, []);
  const { captures, serverReachable, progress, startCapture } = useCaptures(captureGateway, onCaptured);
  const startCaptureFromHere = (url: string) => {
    pageUrlWhenCaptureStarted.current = page.url;
    setCapturedPageToOpen(null);
    startCapture(url);
  };
  const [viewAs, setViewAs] = useState<ViewAs>('team');
  const [previewMode, setPreviewMode] = useState<PreviewMode>('approved');
  const [selectedIds, setSelectedIds] = useState<Record<string, string | null>>({});
  // What the reviewer picked for each page. A page nobody has picked on yet gets sensible defaults below.
  const [versionIdByPage, setVersionIdByPage] = useState<Record<string, string>>({});
  const [groupIdByPage, setGroupIdByPage] = useState<Record<string, string>>({});

  // The version with suggestions comes first, so a new page does not open on an empty list.
  const version =
    session?.versions.find((v) => v.id === versionIdByPage[page.url]) ??
    session?.versions.find((v) => v.suggestions.length > 0) ??
    session?.versions[0];
  const groups = useMemo(
    () => (session && version ? groupSuggestions(session.lessonTabs, version.suggestions) : []),
    [session, version],
  );
  const activeGroupId = groups.find((g) => g.id === groupIdByPage[page.url])?.id ?? groups[0]?.id ?? '';
  const setActiveGroupId = (groupId: string) => setGroupIdByPage((ids) => ({ ...ids, [page.url]: groupId }));
  const setActiveVersionId = (versionId: string) =>
    setVersionIdByPage((ids) => ({ ...ids, [page.url]: versionId }));
  const isVisitor = viewAs === 'visitor';
  const showApproved = isVisitor || previewMode === 'approved';

  // Until this page's review has arrived, `session` is still the previous page's. Its approved changes
  // belong to that page, so none of them are applied here.
  const patches = useMemo(
    () =>
      session && version && showApproved && !isLoading
        ? appliedSuggestions(session, version.id).flatMap((s) => s.patches)
        : [],
    [session, version, showApproved, isLoading],
  );

  // Clicking a tab inside the lesson moves the review panel to that tab's suggestions.
  const lessonTabs = session?.lessonTabs;
  const onLessonTabChange = useCallback(
    (tabId: string) => {
      if (lessonTabs?.some((tab) => tab.id === tabId)) {
        setGroupIdByPage((ids) => ({ ...ids, [page.url]: tabId }));
      }
    },
    [lessonTabs, page.url],
  );

  if (!session || !version) {
    return (
      <div className="app">
        <AppHeader viewAs={viewAs} onViewAsChange={setViewAs} />
        <p className={error ? 'load-message error' : 'load-message'} role={error ? 'alert' : 'status'}>
          {error ?? 'Loading the review…'}
        </p>
      </div>
    );
  }

  // Nothing is open until the reviewer picks a suggestion, so a new page opens on the whole list.
  const selectedId = selectedIds[version.id] ?? null;
  const selected = isLoading
    ? undefined
    : suggestionsInGroup(version.suggestions, groups, activeGroupId).find((s) => s.id === selectedId);
  // The lesson switches to the tab the reviewer is looking at. The whole-page group is not a tab.
  const previewTabId = session.lessonTabs.some((tab) => tab.id === activeGroupId) ? activeGroupId : null;

  return (
    <div className="app">
      <AppHeader viewAs={viewAs} onViewAsChange={setViewAs} />
      {!isVisitor && (
        <CaptureBar
          samplePage={samplePage}
          page={page}
          captures={captures}
          serverReachable={serverReachable}
          progress={progress}
          onCapture={startCaptureFromHere}
          onPageChange={setPage}
          capturedPageToOpen={capturedPageToOpen?.url === page.url ? null : capturedPageToOpen}
        />
      )}
      <main className={isVisitor ? 'workspace workspace-visitor' : 'workspace'}>
        <PagePreview
          url={page.url}
          addressLabel={`${page.label} · ${version.shortName} version`}
          patches={patches}
          targetFrame={session.targetFrame}
          highlightSelector={isVisitor ? null : (selected?.targetSelector ?? null)}
          tabId={previewTabId}
          onLessonTabChange={onLessonTabChange}
          controls={
            isVisitor ? (
              <SegmentedControl
                label="Page version"
                value={version.id}
                onChange={setActiveVersionId}
                options={session.versions.map((v) => ({
                  value: v.id,
                  label: capitalize(v.shortName),
                }))}
              />
            ) : (
              <SegmentedControl
                label="Page shown"
                value={previewMode}
                onChange={setPreviewMode}
                options={[
                  { value: 'approved', label: 'With approved changes' },
                  { value: 'original', label: 'Original' },
                ]}
              />
            )
          }
        />
        {!isVisitor && (
          <ReviewPanel
            session={session}
            version={version}
            selectedId={selectedId}
            groups={groups}
            activeGroupId={activeGroupId}
            isLoading={isLoading}
            error={error}
            onGroupChange={setActiveGroupId}
            onVersionChange={setActiveVersionId}
            onSelect={(id) => setSelectedIds((ids) => ({ ...ids, [version.id]: id }))}
            onDecide={decide}
            onSeeVisitorView={() => setViewAs('visitor')}
          />
        )}
      </main>
    </div>
  );
}
