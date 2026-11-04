# TVO_Chameleon
Group 4 repo for FTL 2026

## Running the app

The capture server (`server.js`) pulls a TVO Learn page into a static copy, and the client (`client/`)
shows that copy next to the review panel.

Two processes run side by side. Start the analysis backend first (see "Backend" below for the model settings):

```
cd backend
uv sync
uv run python -m nltk.downloader cmudict    # first run only: the readability metrics need this word list
MODEL_MOCK=1 uv run uvicorn main:app --port 8001
```

Then, from the repository root, start the capture server, which also serves the client and forwards
`/backend/analyze` and `/backend/adapted` to the backend (set `BACKEND_URL` if it is not on port 8001):

```
npm install
npx playwright install chromium
npm run build:client
npm start
```

Open http://localhost:3000, paste a TVO Learn link and press "Capture page". A capture can take a few minutes.

For client development, run `npm start` in the repository root and `npm run dev` in `client/`
(http://localhost:5173 forwards `/api` and `/snapshots` to the server). See `client/README.md`.

## Backend

The one HTTP service the frontend talks to (Interface 3: UI <-> Backend). It wraps
`dyslexia_engine/` as a plain Python library — rule engine + model layer — so there
is no second server and no MCP hop in the serving path.

```bash
cd backend
uv sync
MODEL_MOCK=1 uv run uvicorn main:app --port 8001   # mock model, no key needed
```

To use the Claude API instead of the mock, put this in `dyslexia_engine/.env`
(git-ignored) or export it:

```bash
MODEL_BASE_URL=https://api.anthropic.com/v1
MODEL_NAME=claude-sonnet-5-5
MODEL_API_KEY=<your Anthropic API key>
```

Ollama / RunPod work the same way — see `dyslexia_engine/.env.example` and
`dyslexia_engine/app/model/README.md`. No code changes, env vars only.

| Endpoint | Does |
|---|---|
| `POST /analyze {html}` | rule-engine recs + model text recs, all status `pending` |
| `POST /adapted {html, recommendations}` | applies only `accepted`/`edited` ones, returns adapted HTML + injected CSS |

The frontend keeps accept/deny/edit state itself (it already does) and sends the
final statuses to `/adapted` — the backend is stateless. Send the **same HTML** to
both endpoints; block ids are resolved against it.

## dyslexia_engine

The engine and model layer (see `dyslexia_engine/readme.md`). Its own FastMCP
server (`python -m app.main`) still exists for MCP clients, but the backend above
imports the engine directly.
