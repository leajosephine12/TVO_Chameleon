# samples/

Saved examples for a demo fallback (use these if no model is running).

- `text_recs_input.json`: two real TVO Learn paragraphs plus **FAKE** findings (flagged `FAKE_SAMPLE_DATA`).
- `text_recs_output.json`: the list of recommendations (the exact shape `/analyze` expects), produced by the **mock**, not a real model.

- `layout_recs_input.json` / `layout_recs_output.json`: the same for the layout call (fake DOM metrics; the screenshot is a tiny placeholder).
- `adapted_ui_input.json` / `adapted_ui_output.json`: call 3 (plain code): the accepted recommendations in, the adapted-page spec out. The spec schema is a **placeholder**.

Regenerate with `python scripts/save_samples.py` from `dyslexia_backend/`.
