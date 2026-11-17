# Architecture: dyslexia_engine

`dyslexia_engine` is a Python library that adapts a page for readers with dyslexia.
It has no server of its own: `backend/main.py` (the gateway) imports
`app.adaptation_engine` and calls `analyze` and `apply` directly. The gateway also
calls other engines such as `general_accessibility_engine`. This library knows nothing
about those engines or about the frontend.

Rules in code decide what is wrong, the model rewrites text (level 2 only), the human
decides, and code applies. Every recommendation carries its citation.

```mermaid
flowchart TD
    FE["Frontend<br/>holds accept / deny / edit state"]

    subgraph GW["backend/main.py (gateway, FastAPI)<br/>owns CORS / auth / routing, merges engines"]
        EP["POST /analyze · POST /adapted"]
    end

    OTHER["general_accessibility_engine<br/>(other engines)"]

    subgraph DYS["dyslexia_engine/app (Python library, no server)"]
        ENG["adaptation_engine.py<br/>analyze(level) · apply(level)"]

        subgraph L1["Level 1: representation (code only)"]
            A1["levels/level1_representation.py<br/>analyze_level1 · apply_level1"]
            G1["guidelines/level1_representation.py<br/>values + sources (source of truth)<br/>evidence_for(ids)"]
        end

        subgraph L2["Level 2: plain text (model)"]
            A2["levels/level2_plain_text.py<br/>analyze_level2 · apply_level2"]
            G2["guidelines/level2_plain_text.py"]
            P2["model/per_level_prompts/<br/>level2_plain_text.py (builds the prompt)"]
            RUN["model/runner.py + guards.py<br/>validate model output"]
            CL["model/client.py<br/>OpenAI-format POST"]
        end
    end

    MODEL["Model endpoint (env vars only)<br/>Claude · Ollama/Gemma · MODEL_MOCK=1"]

    FE -->|"HTTP"| EP
    EP -->|"Python call: engine.analyze / engine.apply<br/>(level + html or blocks)"| ENG
    EP -.-> OTHER
    ENG -->|level 1| A1
    ENG -->|level 2| A2
    A1 --> G1
    A2 --> G2
    A2 --> P2 --> RUN --> CL -->|"POST /chat/completions"| MODEL
```

## How the gateway calls the engine

```python
from app import adaptation_engine as engine

result = engine.analyze(1, html=html)                       # level 1, no model call
result = engine.analyze(2, blocks=blocks)                   # level 2, calls the model
adapted = engine.apply(1, html=html, accepted=recs)         # AdaptResult
adapted = engine.apply(2, blocks=blocks, accepted=recs)     # Level2ApplyResult
```

The gateway imports the module under the alias `engine` because it defines its own
`analyze` endpoint function, which would otherwise shadow the engine's `analyze`.

## Flow

1. The gateway receives `POST /analyze {level, html | blocks, ...}` from the frontend
   and calls `engine.analyze(level, ...)`.
2. `adaptation_engine.analyze(level, ...)` routes by `level`:
   - **Level 1** takes an HTML string and runs `analyze_level1`. One recommendation per
     offending element (italics, underline, inline styles) plus one per page-wide rule
     group (typography, spacing, color, layout, emphasis). No model call.
   - **Level 2** takes text blocks `[{"block_id", "text"}]` and runs `analyze_level2`.
     It builds the prompt from `per_level_prompts/`, calls the model through
     `runner.py`, and guards check the output before it is returned.
3. The result is an `AnalyzeResult {level, recommendations, findings}`. Every
   recommendation is `pending`. Nothing has been changed yet.
4. The user accepts, denies or edits each one. **State lives in the frontend and the
   gateway**; the library is stateless.
5. The gateway receives `POST /adapted {level, html | blocks, recommendations}`, keeps
   only `accepted` and `edited` (and `pending`, which the orchestrator treats as
   accepted), then calls `engine.apply(level, ...)`, which routes:
   - **Level 1:** `apply_level1` edits elements and injects one `<style data-dyslexia-adapt>`
     with only the accepted page-wide sections. Returns `AdaptResult`.
   - **Level 2:** `apply_level2` applies the accepted text rewrites. Returns `Level2ApplyResult`.
6. Send the **same** `html` / `blocks` to both calls. Block ids (`p-4`) resolve against it.

## Level mapping

| Level | Input | Method | Model? | Entry points |
|---|---|---|---|---|
| 1 Representation | `html` | Deterministic CSS and element edits | No | `analyze_level1`, `apply_level1` |
| 2 Plain text | `blocks` | Model rewrites, validated by guards | Yes | `analyze_level2`, `apply_level2` |
| 3+ | n/a | Not implemented (`SUPPORTED_LEVELS = (1, 2)`) | n/a | n/a |

## Contracts

- `Recommendation` (`app/schemas.py`) is the one shared object between this library, the
  model layer and the gateway.
- **Evidence comes from the guideline's own `source` field.** Level 1 builds it with
  `evidence_for("L1.1.7")`, which looks the id up in `guidelines/level1_representation.py`
  and returns e.g. `L1.1.7: Scope. (2023) ...`. Nothing is hard-coded in the analyzer.
  Add a guideline once and its citation follows everywhere.
- Level 1 numbers (font size, spacing, colors, line length) live only in
  `guidelines/level1_representation.py`.
- Model choice is environment only: `MODEL_BASE_URL`, `MODEL_NAME`, `MODEL_API_KEY`,
  `MODEL_TEMPERATURE`, or `MODEL_MOCK=1`. Loaded from `dyslexia_engine/.env`.
- Errors: `adaptation_engine` raises `ValueError` for an unsupported level or missing
  `html` / `blocks`, and level 2 raises on model problems. The gateway turns these into
  `422` (bad request) and `502` (model unavailable).

## Folder structure

```
dyslexia_engine/app/
├── schemas.py              # shared Recommendation / AnalyzeResult / AdaptResult
├── adaptation_engine.py    # thin orchestrator: analyze(level), apply(level)
├── guidelines/
│   ├── __init__.py         # get_guidelines(level=None)
│   ├── level1_representation.py   # values, sources, PAGE_RULES, evidence_for
│   └── level2_plain_text.py
├── levels/
│   ├── level1_representation.py   # analyze_level1, apply_level1
│   └── level2_plain_text.py       # analyze_level2, apply_level2
└── model/                  # model layer (shared plumbing + per-level prompts)
    ├── per_level_prompts/level2_plain_text.py   # builds the level 2 prompt
    ├── client.py, config.py, log.py, guards.py, runner.py
    ├── analyze_level2.py
    └── schemas.py, sample_data.py, standin_analyze_text.py
```

## Out of scope here (handled by the gateway or other engines)

- The HTTP API, CORS and auth (`backend/main.py`).
- Calling and merging `general_accessibility_engine`.
- Rendering a URL with Playwright, screenshots, axe, layout metrics.
- Combining adapted HTML from several engines.

## Known gaps

- Level 1 checks only the page's own CSS, not computed browser styles.
- Level 1 element ids (`<tag>-<n>`) shift after `<i>/<em>/<u>` are rewritten, so always
  apply against the HTML that was analyzed.
- Levels beyond 2 are not implemented.
- The old FastMCP server (`get_guidelines`, `analyze_html`, `apply_recommendations`) is
  not part of the library. Move it to its own file if MCP clients are still needed.