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
