# TVO_Chameleon
Group 4 repo for FTL 2026

## MCP server

FastMCP server exposing page-analysis tools (Interface 2: Backend <-> MCP). All tools are currently **mocks** returning fixed JSON in the agreed shapes.

```bash
cd MCP_server
uv run mcp_server.py   # serves http://localhost:8000/mcp (PORT env var to change)
```

| Tool | In | Out |
|---|---|---|
| `fetch_page` | url | text blocks with IDs/selectors + screenshot (null for now) |
| `analyze_text` | blocks | long sentences, readability scores, difficult words |
| `structure_checks` | url | static DOM checks (headings, lists, link text, landmarks) |
| `run_axe` | url | WCAG violations |
| `layout_metrics` | url | font size, line spacing, line length |

## Backend

Placeholder FastAPI backend (Interface 3: UI <-> Backend). It runs the agent loop: calls Claude, executes requested tools against the MCP server, feeds results back until Claude returns recommendations. Swapping to a local OpenAI-compatible model later only replaces the model call, not the loop.

```bash
export ANTHROPIC_API_KEY=...   # or `ant auth login`
cd backend
uv run uvicorn main:app --port 8001   # MCP server must be running on :8000
```

| Endpoint | Does |
|---|---|
| `POST /analyze {url}` | agent loop -> list of recommendations |
| `POST /recommendations/{id}/decision` | store accept/deny/edit (in-memory) |
| `GET /adapted?url=...` | placeholder, returns stored decisions |
