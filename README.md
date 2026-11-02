# TVO_Chameleon
Group 4 repo for FTL 2026

## Backend

The one HTTP service the frontend talks to (Interface 3: UI <-> Backend). It wraps
`dyslexia_backend/` as a plain Python library — rule engine + model layer — so there
is no second server and no MCP hop in the serving path.

```bash
cd backend
uv sync
MODEL_MOCK=1 uv run uvicorn main:app --port 8001   # mock model, no key needed
```

To use the Claude API instead of the mock, put this in `dyslexia_backend/.env`
(git-ignored) or export it:

```bash
MODEL_BASE_URL=https://api.anthropic.com/v1
MODEL_NAME=claude-sonnet-5-5
MODEL_API_KEY=<your Anthropic API key>
```

Ollama / RunPod work the same way — see `dyslexia_backend/.env.example` and
`dyslexia_backend/app/model/README.md`. No code changes, env vars only.

| Endpoint | Does |
|---|---|
| `POST /analyze {html}` | rule-engine recs + model text recs, all status `pending` |
| `POST /adapted {html, recommendations}` | applies only `accepted`/`edited` ones, returns adapted HTML + injected CSS |

The frontend keeps accept/deny/edit state itself (it already does) and sends the
final statuses to `/adapted` — the backend is stateless. Send the **same HTML** to
both endpoints; block ids are resolved against it.

## dyslexia_backend

The engine and model layer (see `dyslexia_backend/readme.md`). Its own FastMCP
server (`python -m app.main`) still exists for MCP clients, but the backend above
imports the engine directly.
