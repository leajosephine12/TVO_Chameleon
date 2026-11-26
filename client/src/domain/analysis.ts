/**
 * What the analysis backend (backend/main.py) sends and receives. The field names are the backend's
 * `Recommendation` contract (dyslexia_engine/app/schemas.py), so they stay in snake_case.
 */
export type RecommendationStatus = 'pending' | 'accepted' | 'denied' | 'edited';

export interface Recommendation {
  id: string;
  /** "<tag>-<n>": the n-th such tag in the analysed HTML, for example "p-4". "page" for page-wide rules. */
  block_id: string;
  /** For example "italic_text", "typography", "long_sentence". */
  type: string;
  original: string;
  suggestion: string;
  rationale: string;
  evidence: string;
  severity: 'low' | 'medium' | 'high';
  status: RecommendationStatus;
  /** The fields below are only set by the general accessibility analysis (backend/genui). */
  title?: string | null;
  /** "reading", "cognitive" or "wcag". */
  category?: string | null;
  /** The HTML that replaces the block once the change is applied, built by the backend's renderer. */
  preview_html?: string | null;
  /** CSS declarations for the block, for a style change such as "font-size: 16px; line-height: 1.5". */
  preview_css?: string | null;
}

export interface Analysis {
  recommendations: Recommendation[];
  /** Set when the model step failed: it could not be reached, gave unusable output or is set up wrongly. The rule-based recommendations are still there. */
  modelError: string | null;
}

export interface GeneralAnalysis extends Analysis {
  /** Set when the page could not be rendered, so text size, line spacing and line length were not checked. */
  layoutError: string | null;
}

/** The result of applying the accepted recommendations. Only the CSS is needed to preview page-wide rules. */
export interface Adaptation {
  injectedCss: string;
  applied: string[];
  skipped: string[];
}
