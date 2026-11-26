import type { ReviewVersion } from '../domain/review';
import { capitalize } from './labels';
import { SegmentedControl } from './SegmentedControl';

interface Props {
  versions: ReviewVersion[];
  versionId: string;
  onVersionChange: (versionId: string) => void;
  /** How many approved changes the visitor gets in this version, including those it builds on. */
  appliedCount: number;
  onBackToReview: () => void;
}

/**
 * The bar above the page in the visitor view: which version a visitor reads, how many approved changes it
 * has, and the way back to reviewing.
 */
export function VisitorControls({
  versions,
  versionId,
  onVersionChange,
  appliedCount,
  onBackToReview,
}: Props) {
  return (
    <div className="visitor-controls">
      <span className="visitor-controls-label">Reading version</span>
      <SegmentedControl
        label="Reading version"
        value={versionId}
        onChange={onVersionChange}
        options={versions.map((v) => ({ value: v.id, label: capitalize(v.shortName) }))}
      />
      <span className="applied-count" role="status">
        {appliedCount} approved {appliedCount === 1 ? 'change' : 'changes'} applied
      </span>
      <button type="button" className="back-to-review" onClick={onBackToReview}>
        Back to review
      </button>
    </div>
  );
}
