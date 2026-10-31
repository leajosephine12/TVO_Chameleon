# Dyslexia backend (Level 1)

Takes education HTML extracted from an iframe, recommends dyslexia-friendly changes, and applies only the ones the user accepts.

## Pipeline

```
Frontend (iframe HTML)
   -> Backend / AI model (FastMCP Client)
      -> FastMCP server   app/main.py          tools: get_guidelines, analyze_html, apply_recommendations
         -> Python engine app/adaptation_engine.py
            -> rules      app/guidelines.py     research values, single source of truth
```

The MCP tools take JSON in and return JSON out, with no model inside. The engine is plain Python, so it can be called directly too.

## Flow (matches the team contract)

1. `analyze_html(html)` returns `Recommendation` objects, all `status: "pending"`.
2. The UI shows them. The backend records accept / deny / edit by changing `status`.
3. `apply_recommendations(html, recommendations)` applies only `accepted` and `edited` ones.

## Recommendation format

```json
{
  "id": "r1", "block_id": "em-1", "type": "italic_text",
  "original": "<em>by which</em>", "suggestion": "<strong>by which</strong>",
  "rationale": "...", "evidence": "Level 1 guideline L1.1.7",
  "severity": "low", "status": "pending"
}
```

- `block_id` is `<tag>-<n>`, the n-th tag in document order (like `p-4`). Page-wide rules use `page`.
- Always send the same HTML to `analyze_html` and `apply_recommendations`.
- Element types: `italic_text`, `underline_text`, `inline_style`. Page-wide types: `typography`, `spacing`, `color`, `layout`, `emphasis`.
- For `edited` element recommendations, put the user's replacement HTML (or style string) in `suggestion`.

## Run

```bash
pip install -r requirements.txt
python demo_client.py                              # in-memory demo
python -m app.main --http                          # serve at http://127.0.0.1:8000/mcp
python demo_client.py http://127.0.0.1:8000/mcp    # demo against the running server
python -m app.main                                 # stdio, for MCP clients
```

Open `demo/sample_iframe.html` and `demo/sample_adapted.html` side by side. The demo denies the layout rule, so the adapted page keeps its two columns.

## To agree with the other backend person

- Tool names. Mine are `get_guidelines`, `analyze_html`, `apply_recommendations`. Is this a second MCP server or are they added to theirs?
- Their tools take a `url`, mine take HTML. Confirm which one they want.
- The REST endpoints (`/analyze`, `/decision`, `/adapted`) belong to the general backend, not this service.

## Assumptions to confirm

- Average letter width is 0.5em, so letter spacing is 0.175em and word spacing 0.613em.
- Links are bold and coloured but not underlined. This can conflict with WCAG 1.4.1.
- Page-wide recommendations are always offered (computed browser styles are not available from raw HTML), and rated high severity only when the page's own CSS shows the problem.