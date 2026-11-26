import { useSlidingHighlight } from './useSlidingHighlight';

interface Option<T extends string> {
  value: T;
  label: string;
}

interface Props<T extends string> {
  label: string;
  options: Option<T>[];
  value: T;
  onChange: (value: T) => void;
}

/** A row of buttons where exactly one is chosen, such as Team review / Visitor. The highlight slides between them. */
export function SegmentedControl<T extends string>({ label, options, value, onChange }: Props<T>) {
  const { containerRef, highlightStyle } = useSlidingHighlight(
    options.findIndex((option) => option.value === value),
  );

  return (
    <div className="segmented" role="group" aria-label={label} ref={containerRef}>
      <span className="switch-highlight" aria-hidden="true" style={highlightStyle} />
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={option.value === value}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
