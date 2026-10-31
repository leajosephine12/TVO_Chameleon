import { createHttpCaptureGateway } from './infrastructure/httpCaptureGateway';
import { createLocalReviewRepository } from './infrastructure/localReviewRepository';
import { samplePage, sampleVersions } from './infrastructure/sampleSession';
import { ReviewWorkspace } from './ui/ReviewWorkspace';

// The one place that chooses the data sources. Swap the repository when the analysis backend is ready.
const repository = createLocalReviewRepository(samplePage, sampleVersions);
const captureGateway = createHttpCaptureGateway();

/** Root component. */
export default function App() {
  return <ReviewWorkspace repository={repository} captureGateway={captureGateway} samplePage={samplePage} />;
}
