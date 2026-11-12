import type { Adaptation, Analysis, GeneralAnalysis, Recommendation } from '../domain/analysis';
import type { CaptureJob, PageCapture } from '../domain/capture';
import type { ReviewedPage, ReviewSession, ReviewStatus } from '../domain/review';

/** What the app needs from a data source. A server-backed version implements this same interface. */
export interface ReviewRepository {
  loadSession(page: ReviewedPage): Promise<ReviewSession>;
  saveDecision(suggestionId: string, status: ReviewStatus): Promise<void>;
}

/** What the app needs from the capture tool. */
export interface CaptureGateway {
  listCaptures(): Promise<PageCapture[]>;
  startCapture(url: string): Promise<string>;
  getJob(jobId: string): Promise<CaptureJob>;
}

/** What the app needs from the analysis backend. All calls must be given the same HTML. */
export interface AnalysisGateway {
  /** The dyslexia rules (fonts, spacing, colours, italics). */
  analyze(html: string): Promise<Analysis>;
  /** General accessibility. `url` is where the backend can open the same page to measure its layout. */
  analyzeGeneral(html: string, url: string): Promise<GeneralAnalysis>;
  adapt(html: string, recommendations: Recommendation[]): Promise<Adaptation>;
}
