import { useCallback, useMemo, useState } from 'react';
import type { CaptureGateway, ReviewRepository } from '../application/ports';
import { useCaptures } from '../application/useCaptures';
import { useReviewSession } from '../application/useReviewSession';
import { pageFromCapture, type PageCapture } from '../domain/capture';
import { appliedSuggestions, rankSuggestions, type ReviewedPage } from '../domain/review';
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
  const { session, error, decide } = useReviewSession(repository, page);
  const onCaptured = useCallback((capture: PageCapture) => setPage(pageFromCapture(capture)), []);
  const { captures, serverReachable, progress, startCapture } = useCaptures(captureGateway, onCaptured);
  const [viewAs, setViewAs] = useState<ViewAs>('team');
  const [previewMode, setPreviewMode] = useState<PreviewMode>('approved');
  const [activeVersionId, setActiveVersionId] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Record<string, string>>({});

  const version = session?.versions.find((v) => v.id === activeVersionId) ?? session?.versions[0];
  const isVisitor = viewAs === 'visitor';
  const showApproved = isVisitor || previewMode === 'approved';

  const patches = useMemo(
    () =>
      session && version && showApproved
        ? appliedSuggestions(session, version.id).flatMap((s) => s.patches)
        : [],
    [session, version, showApproved],
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

  const selectedId = selectedIds[version.id] ?? rankSuggestions(version.suggestions)[0]?.id ?? '';
  const selected = version.suggestions.find((s) => s.id === selectedId);

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
          onCapture={startCapture}
          onPageChange={setPage}
        />
      )}
      <main className={isVisitor ? 'workspace workspace-visitor' : 'workspace'}>
        <PagePreview
          url={page.url}
          addressLabel={`${page.label} · ${version.shortName} version`}
          patches={patches}
          highlightSelector={isVisitor ? null : (selected?.targetSelector ?? null)}
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
            error={error}
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
