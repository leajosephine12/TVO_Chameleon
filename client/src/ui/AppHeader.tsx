import type { ReactNode } from 'react';
import { SegmentedControl } from './SegmentedControl';

export type ViewAs = 'team' | 'visitor';

interface Props {
  viewAs: ViewAs;
  onViewAsChange: (viewAs: ViewAs) => void;
  /** Shown between the name and the view switch, such as the page picker and the capture button. */
  children?: ReactNode;
}

/** The one bar across the top: the app's name, what is being reviewed, and who the page is shown as. */
export function AppHeader({ viewAs, onViewAsChange, children }: Props) {
  return (
    <header className="app-header">
      <span className="logo" aria-hidden="true" />
      <h1>TVO Chameleon</h1>
      {children}
      <div className="view-as">
        <span id="view-as-label">View as</span>
        <SegmentedControl
          label="View as"
          value={viewAs}
          onChange={onViewAsChange}
          options={[
            { value: 'team', label: 'Team review' },
            { value: 'visitor', label: 'Visitor' },
          ]}
        />
      </div>
    </header>
  );
}
