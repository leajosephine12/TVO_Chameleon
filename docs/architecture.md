# Architecture (current)

One HTTP backend; `dyslexia_engine` is a library inside it, not a second service.
The model never calls tools — the backend makes fixed, validated calls and does the
deterministic work in plain Python.

```mermaid
flowchart TD
    subgraph FE["Frontend (Integration branch)"]
        CAP["capture.js<br/>pulls TVO page / iframe HTML"]
        UI["React client<br/>review panel: accept / deny / edit"]
    end

    subgraph BE["backend/ (FastAPI, :8001 — the only server)"]
        AN["POST /analyze {html}"]
        AD["POST /adapted {html, recommendations}"]
    end

    subgraph LIB["dyslexia_engine/ (imported as a library)"]
        ENG["app/adaptation_engine.py<br/>rule engine: analyze_level1, apply_level1"]
        GL["app/guidelines.py<br/>research values (source of truth)"]
        subgraph ML["app/model/ (Vriti)"]
            SA["standin_analyze_text<br/>readability findings, plain code"]
            C1["call 1: generate_text_recommendations"]
            C2["call 2: generate_layout_recommendations<br/>(not wired — needs a screenshot)"]
            C3["call 3: generate_adapted_ui<br/>plain-code apply spec"]
            CL["client.py — OpenAI-format POST"]
        end
    end

    MODEL["Model endpoint (env vars only)<br/>Claude API · Ollama/Gemma 4 · MODEL_MOCK=1"]

    CAP --> UI
    UI -->|html| AN
    UI -->|html + final statuses| AD
    AN --> ENG
    AN --> SA --> C1
    AD --> ENG
    AD --> C3
    ENG --> GL
    C1 --> CL
    C2 -.-> CL
    CL -->|"POST /chat/completions"| MODEL

    MCP["app/main.py — FastMCP server (Pongpang)<br/>get_guidelines · analyze_html · apply_recommendations"]
    MCP -. "same engine, side door for MCP clients<br/>(not in the serving path)" .-> ENG
```

## Flow

1. Capture tool extracts the TVO page/iframe HTML.
2. `POST /analyze {html}` → rule-engine recommendations (`analyze_level1`) plus
   model text recommendations (`standin_analyze_text` → call 1). All `pending`.
3. The UI shows them; the user accepts / denies / edits. **State lives in the
   frontend** — the backend is stateless.
4. `POST /adapted {html, recommendations}` → engine types via `apply_level1`,
   model text types via `generate_adapted_ui`. Returns adapted HTML + injected CSS.
   Send the same HTML as in step 2 — block ids (`p-4`) resolve against it.

## Contracts

- `Recommendation` (`app/schemas.py`) is the one shared object: frontend,
  engine, and model layer all speak it.
- Model choice is environment only (`MODEL_BASE_URL`, `MODEL_NAME`,
  `MODEL_API_KEY`, or `MODEL_MOCK=1`) — see the root README.

## Known gaps

- Rendered metrics deferred: L7 style variance, L8 density, L9/L10 fold checks,
  and the paragraph-spacing half of L2.
- Bucket 2 (spaCy/embeddings) and bucket 3 (multi-page crawl) of the metrics map.
- Applying a model text edit replaces the block's text wholesale (drops inline
  tags inside the block).
- Levels beyond 1 are not implemented.
