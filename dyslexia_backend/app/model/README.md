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

## Stand-in for `analyze_text`

`app/model/standin_analyze_text.py` is a **stand-in** (plain code, no model) that produces findings in the proposed shape, so call 1 can run end to end today:

```python
findings = standin_analyze_text(blocks)
recs = generate_text_recommendations(blocks, findings)
```

It is flagged `"STAND_IN": true` in its output. Replace it with the team's real `analyze_text` when that exists. Its readability grade is Flesch-Kincaid and its syllable, sentence and difficult-word detection are rough heuristics.

## Call 3: `generate_adapted_ui` (placeholder GenUI spec)

> **The spec is a placeholder** (`app/model/adapted_ui_spec.py`): `{"changes": [{"block_id", "action": "replace_text|set_style", "value"}]}`. Swap the real schema in that file and in the two builders.

```python
result = generate_adapted_ui(text_recs, layout_recs, blocks)   # plain code (recommended, default)
result = generate_adapted_ui(text_recs, layout_recs, blocks, use_model=True)   # model version
result.spec      # the placeholder spec
result.skipped   # accepted recommendations that could not become a change, each with a reason
```

- Only `accepted` / `edited` recommendations are used; pending and denied are ignored. For `edited`, `suggestion` holds the user's own text.
- `blocks` is needed because `replace_text` carries the whole new block text (one block can have several accepted edits). Question for the GenUI owner: would a phrase-level change (original + replacement) suit the renderer better?
- `set_style` values are checked against a safe list of CSS properties; `replace_text` must be plain text. The renderer must insert it as text, never as HTML.
- Structural suggestions such as "break into steps" are reported in `skipped`, because the placeholder spec cannot express them.

**Recommendation: use the plain-code version.** Once the user has accepted a change, turning it into a spec is deterministic. Code gives the same answer every time, cannot reword what the user approved, needs no model call (no wait on a laptop, no cost), and is easy to test. The model version needs checks that force its output to equal the code's result, so it adds risk and delay and no value. A model would only help if the spec needed judgement, for example turning "break into steps" into real UI structure, and that depends on the real GenUI schema. Revisit then.
