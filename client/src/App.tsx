import { createAnalysisReviewRepository } from './infrastructure/analysisReviewRepository';
import { createHttpAnalysisGateway } from './infrastructure/httpAnalysisGateway';
import { createHttpCaptureGateway } from './infrastructure/httpCaptureGateway';
import { createLocalReviewRepository } from './infrastructure/localReviewRepository';
import { samplePage, sampleVersions } from './infrastructure/sampleSession';
import { ReviewWorkspace } from './ui/ReviewWorkspace';

// The one place that chooses the data sources. Captured pages are analysed by the backend; the sample page keeps its sample suggestions.
const repository = createAnalysisReviewRepository(
  createLocalReviewRepository(samplePage, sampleVersions),
  createHttpAnalysisGateway(),
  samplePage,
);
const captureGateway = createHttpCaptureGateway();

/** Root component. */
export default function App() {
  return <ReviewWorkspace repository={repository} captureGateway={captureGateway} samplePage={samplePage} />;
}
