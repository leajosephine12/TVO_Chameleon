import express from 'express';

// The analysis backend (backend/main.py, FastAPI) is a separate service. The review client only talks
// to this server, so its requests stay on one origin and the backend needs no CORS setup.
const ALLOWED_ENDPOINTS = ['analyze', 'adapted'];
const MAX_BODY = '50mb'; // a captured lesson is about 1 MB of HTML
const BACKEND_TIMEOUT_MS = 10 * 60 * 1000; // the model calls behind /analyze can take minutes

/**
 * Forwards POST /backend/analyze and POST /backend/adapted to the analysis backend, unchanged.
 * Only those two endpoints are forwarded, so this cannot be used to reach anything else on the backend.
 *
 * @param {string} backendUrl  where the backend listens, for example http://localhost:8001
 */
export function createBackendProxy(backendUrl) {
    const router = express.Router();

    router.post(
        `/:endpoint(${ALLOWED_ENDPOINTS.join('|')})`,
        express.raw({ type: 'application/json', limit: MAX_BODY }),
        async (req, res) => {
            try {
                const response = await fetch(`${backendUrl}/${req.params.endpoint}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: req.body,
                    signal: AbortSignal.timeout(BACKEND_TIMEOUT_MS),
                });
                res.status(response.status).type('json').send(Buffer.from(await response.arrayBuffer()));
            } catch {
                res.status(502).json({
                    error: `The analysis backend did not respond at ${backendUrl}. Is it running? (see README)`,
                });
            }
        }
    );

    return router;
}
