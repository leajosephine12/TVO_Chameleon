# samples/

Saved examples for a demo fallback (use these if no model is running).

- `text_recs_input.json`: two real TVO Learn paragraphs plus **FAKE** findings (flagged `FAKE_SAMPLE_DATA`).
- `text_recs_output.json`: the list of recommendations (the exact shape `/analyze` expects), produced by the **mock**, not a real model.

Regenerate with `python scripts/save_samples.py` from `dyslexia_backend/`.
