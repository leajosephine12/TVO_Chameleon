import { useLayoutEffect, useRef, useState, type CSSProperties } from 'react';

/**
 * Places a switch's highlight under its chosen button, so changing the choice slides the highlight across
 * instead of jumping. The size comes from the button itself, so options of different widths work too.
 *
 * @param activeIndex the position of the chosen button among the switch's buttons
 * @returns a ref for the switch's container and the style for its highlight element
 */
export function useSlidingHighlight(activeIndex: number) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [highlightStyle, setHighlightStyle] = useState<CSSProperties>({ opacity: 0 });
  // The first placement happens before anything is shown, so it must not animate in from the left edge.
  const isPlaced = useRef(false);

  useLayoutEffect(() => {
    const container = containerRef.current;
    if (!container) return undefined;

    const place = () => {
      const button = container.querySelectorAll<HTMLElement>(':scope > button')[activeIndex];
      if (!button) return;
      setHighlightStyle({
        width: button.offsetWidth,
        transform: `translateX(${button.offsetLeft}px)`,
        ...(isPlaced.current ? {} : { transition: 'none' }),
      });
      isPlaced.current = true;
    };
    place();

    // Fonts loading or the window resizing change the buttons' widths, so measure again then.
    if (typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(place);
    observer.observe(container);
    return () => observer.disconnect();
  }, [activeIndex]);

  return { containerRef, highlightStyle };
}
