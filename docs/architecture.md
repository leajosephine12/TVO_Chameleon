# Architecture (current)

One HTTP backend; `dyslexia_engine` and `accessibility_engine` are libraries inside
it, not separate services. Code measures (findings with citations), the model judges
(fixed, validated calls — plus registered bucket-4 judgements it raises itself),
the human decides, code applies.

```mermaid
flowchart TD
    subgraph FE["Frontend (Integration branch)"]
        CAP["capture.js<br/>pulls TVO page / iframe HTML"]
        UI["React client<br/>review panel: accept / deny / edit"]
    end

    subgraph BE["backend/ (FastAPI, :8001 — the only server)"]
        AN["POST /analyze {html, url?, render?}"]
        AD["POST /adapted {html, recommendations}"]
    end

    subgraph ACC["accessibility_engine/ (metrics library)"]
        TM["analyze_text<br/>T1-T7, S1 (textstat)"]
        SC["structure_checks<br/>S/J/N/M table (DOM only)"]
        RD["rendered.py<br/>Playwright: layout metrics, axe, screenshot"]
        TH["THRESHOLDS + judgement registry<br/>tiers & sources from metrics.pdf"]
    end

    subgraph LIB["dyslexia_engine/ (rules + model layer)"]
        ENG["adaptation_engine.py<br/>analyze_level1, apply_level1"]
        GL["guidelines.py<br/>research values (source of truth)"]
        subgraph ML["app/model/ (Vriti)"]
            C1["call 1: text recommendations<br/>+ bucket-4 judgement checks"]
            C2["call 2: layout recommendations (vision)<br/>+ bucket-4 judgement checks"]
            C3["call 3: generate_adapted_ui<br/>plain-code apply spec"]
            CL["client.py — OpenAI-format POST"]
        end
    end

    MODEL["Model endpoint (env vars only)<br/>Claude Fable API · Ollama/Gemma · MODEL_MOCK=1"]

    CAP --> UI
    UI -->|html| AN
    UI -->|html + final statuses| AD
    AN --> ENG
    AN --> TM
    AN --> SC
    AN -->|"render=true"| RD
    TM -->|findings| C1
    SC -->|findings| C1
    RD -->|"screenshot + DOM metrics"| C2
    AD --> ENG
    AD --> C3
    ENG --> GL
    TM --- TH
    SC --- TH
    RD --- TH
    C1 --> CL
    C2 --> CL
    CL -->|"POST /chat/completions"| MODEL

    MCP["app/main.py — FastMCP server (Pongpang)<br/>get_guidelines · analyze_html · apply_recommendations"]
    MCP -. "same engine, side door for MCP clients<br/>(not in the serving path)" .-> ENG
```

## Flow

1. Capture tool extracts the TVO page/iframe HTML (or `render: true` lets the
   backend render a URL itself: layout metrics, axe run, screenshot).
2. `POST /analyze` → rule-engine recommendations (`analyze_level1`), plus
   `accessibility_engine` findings fed to model call 1 (and call 2 when rendered).
   The model also raises registered bucket-4 judgements, labeled
   `model judgement / <metric_id>`; a guard rejects unregistered ids. All `pending`.
3. The UI shows them with citations; the user accepts / denies / edits. **State
   lives in the frontend** — the backend is stateless.
4. `POST /adapted {html, recommendations}` → engine types via `apply_level1`,
   model text types via `generate_adapted_ui`. Returns adapted HTML + injected CSS.
   Send the same HTML as in step 2 — block ids (`p-4`) resolve against it.

## Contracts

- `Recommendation` (`app/schemas.py`) is the one shared object: frontend,
  engines, and model layer all speak it.
- Findings: `{metric_id, block_id, measured, threshold, source, tier, detail}` —
  thresholds/sources copied from `accessibility_metrics.THRESHOLDS`, never inlined.
- Model choice is environment only (`MODEL_BASE_URL`, `MODEL_NAME`,
  `MODEL_API_KEY`, `MODEL_TEMPERATURE`, or `MODEL_MOCK=1`) — see the root README.

## Known gaps

- Rendered metrics deferred: L7 style variance, L8 density, L9/L10 fold checks,
  and the paragraph-spacing half of L2.
- Bucket 2 (spaCy/embeddings) remains deferred. The GenUI library has an opt-in,
  bounded crawl for J7/J8 and report-only N4; J6, J13, N5, and N9 remain
  deferred because their measurement or action is underspecified (see
  `backend/genui/README.md`).
- Applying a model text edit replaces the block's text wholesale (drops inline
  tags inside the block).
- Levels beyond 1 are not implemented.
