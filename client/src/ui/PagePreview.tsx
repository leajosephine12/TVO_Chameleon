import { useEffect, useState, type ReactNode } from 'react';
import type { Patch } from '../domain/review';
import { applyPatches } from './applyPatches';

interface Props {
  url: string;
  addressLabel: string;
  patches: Patch[];
  highlightSelector: string | null;
  /** Controls shown at the right of the address bar. */
  controls: ReactNode;
}

/** The reviewed page in a browser-style frame. Scripts stay off inside it, like in a captured page. */
export function PagePreview({ url, addressLabel, patches, highlightSelector, controls }: Props) {
  const [doc, setDoc] = useState<Document | null>(null);

  useEffect(() => {
    if (doc) applyPatches(doc, patches, highlightSelector);
  }, [doc, patches, highlightSelector]);

  useEffect(() => {
    if (doc && highlightSelector) {
      doc.querySelector(highlightSelector)?.scrollIntoView({ block: 'center' });
    }
  }, [doc, highlightSelector]);

  return (
    <section className="preview" aria-label="Page preview">
      <div className="preview-bar">
        <span className="dots" aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
        <span className="address">{addressLabel}</span>
        {controls}
      </div>
      <iframe
        title={addressLabel}
        src={url}
        sandbox="allow-same-origin"
        onLoad={(e) => setDoc(e.currentTarget.contentDocument)}
      />
    </section>
  );
}
