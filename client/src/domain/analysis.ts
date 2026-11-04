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
}

export interface Analysis {
  recommendations: Recommendation[];
  /** Set when the model could not be reached. The rule-based recommendations are still there. */
  modelError: string | null;
}

/** The result of applying the accepted recommendations. Only the CSS is needed to preview page-wide rules. */
export interface Adaptation {
  injectedCss: string;
  applied: string[];
  skipped: string[];
}
