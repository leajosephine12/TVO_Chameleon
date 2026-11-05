import { SegmentedControl } from './SegmentedControl';

export type ViewAs = 'team' | 'visitor';

interface Props {
  viewAs: ViewAs;
  onViewAsChange: (viewAs: ViewAs) => void;
}

export function AppHeader({ viewAs, onViewAsChange }: Props) {
  return (
    <header className="app-header">
      <span className="logo" aria-hidden="true" />
      <h1>TVO Chameleon</h1>
      <span className="pill">Concept prototype</span>
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
