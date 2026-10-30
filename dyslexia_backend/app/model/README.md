# Model layer (work in progress)

Full setup instructions and the list of assumptions come in the final README. This file already holds
the part other people need now.

## Findings contract (PROPOSAL for the owner of `analyze_text`)

> **This shape is a proposal, not an agreed contract.** No `analyze_text` exists on the branch yet, so the
> model layer was written against the shape below. If your tool returns something different, tell the
> model-layer owner or change `app/model/sample_data.py` and the prompt in `app/model/text_recs.py`.

`generate_text_recommendations(blocks, findings)` takes:

- `blocks`: the page text, `[{"block_id": "p-1", "text": "..."}]`. Ids are `<tag>-<n>` in document order, the same ids `analyze_html` uses.
- `findings`: the tool's measurements. The model copies numbers from here and never calculates them. Every number in a rationale is checked against this object.

Example input (the numbers are fake):

```json
{
  "blocks": [{"block_id": "p-1", "text": "Students compare different ways ... or taking advantage of sales. ..."}],
  "findings": {
    "targets": {"grade_level": "3-5", "max_sentence_words": "15-20"},
    "blocks": [{
      "block_id": "p-1",
      "word_count": 66,
      "reading_grade": 12.4,
      "long_sentences": [{"text": "Students compare different ways ... advantage of sales.", "word_count": 24}],
      "difficult_words": ["consumers", "compound", "technology"]
    }]
  }
}
```

Example output (a plain list, the team's shared recommendation format, all `pending`):

```json
[{
  "id": "r1", "block_id": "p-1", "type": "long_sentence",
  "original": "Students compare different ways ... advantage of sales.",
  "suggestion": "Students compare different ways ... money. Examples are using reward programs or taking advantage of sales.",
  "rationale": "24 words; Grade 3-5 target <= 15-20",
  "evidence": "readability tool / W3C COGA",
  "severity": "medium", "status": "pending"
}]
```

What the tool must provide: any number a rationale may quote (word counts, grade levels, targets) as a plain number
or inside a string. Extra fields are fine.

## Layout metrics contract (PROPOSAL for the owner of `layout_metrics`)

> Also a proposal. No `layout_metrics` tool exists on the branch yet.

`generate_layout_recommendations(screenshot, metrics)` takes a screenshot (PNG/JPEG/WebP bytes, or base64 text) and:

```json
{"blocks": [{"block_id": "p-1", "font_size_px": 14, "line_height": 1.2, "line_length_chars": 96}]}
```

The reference targets are added by the model layer from `app/guidelines.py` (imported, not copied), so the tool does not send targets.
The output is a plain list of recommendations in the shared format. This call needs a vision-capable model.
