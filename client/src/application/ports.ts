import type { Adaptation, Analysis, Recommendation } from '../domain/analysis';
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

/** What the app needs from the analysis backend. Both calls must be given the same HTML. */
export interface AnalysisGateway {
  analyze(html: string): Promise<Analysis>;
  adapt(html: string, recommendations: Recommendation[]): Promise<Adaptation>;
}
