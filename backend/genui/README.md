# genui: general accessibility, with the model deciding the changes

Code measures the page. The model decides how the page should change. Code checks every proposal, then applies it.
Nothing about wording, headings, labels, lists or styles is hardcoded: those come from the model.

## The flow

```
page HTML
  -> measure.py       the accessibility engine's findings (T, S, J, N, M metrics; L metrics when the page was rendered)
  -> crawl.py         optional, bounded same-origin sample for J7/J8 and report-only N4
  -> context.py       pick the findings the model may act on, and quote the blocks it needs
  -> prompt.py        one prompt, listing only the metrics and typed changes that are on this page
  -> planner.py       ONE model call: {"proposals": [ {metric_id, block_id, rationale, severity, change} ]}
  -> guardrails.py    every proposal runs through the checks below; failures are dropped and reported
  -> select()         page budget and no-overlap rule
  -> preview.py       the renderer builds what each change looks like on the page
  -> recommend.py     Recommendation objects for the review UI (status "pending")
reviewer accepts or denies
  -> service.apply_general   the accepted typed changes, applied by the renderer
```

The Recommendation is the team's shared object plus optional GenUI fields: `title`, `category`, `change`, preview
HTML/CSS, `evidence_type`, and `evidence_websites`. A dyslexia recommendation is still a valid one.

## What the model can change

The model answers with a **typed change**: a closed list defined in
`dyslexia_engine/app/model/adapted_ui_spec.py`. There is no way to send HTML, delete or move an element, or run a script.

| Change | What it does |
|---|---|
| `replace_text` | Rewrites only the flagged words; the rest of the block is untouched |
| `split_paragraph` | Same words, cut into shorter paragraphs |
| `text_to_list`, `split_into_steps` | Turn text into a list or numbered steps |
| `split_list` | One long list becomes several lists under headings |
| `add_section_heading`, `add_heading_before` | Put a heading where one is missing |
| `set_link_text`, `set_button_label`, `add_button_label`, `set_alt_text` | Specific labels and descriptions |
| `explain_term` | Wrap a term in `<abbr title="...">` (visible text unchanged) |
| `stop_autoplay` | Remove autoplay and show the controls |
| `set_style` | A short list of safe CSS properties, with checked values |

## Metrics covered (27 model-actionable metrics)

`policy.py` is the one table that says which metric may be fixed with which change, where, and how many times.
Thresholds always come from `accessibility_engine` (the metrics PDF), never from this package.

- **Measured by code:** T1 T2 T3 T4 T7 T8, S1 S2 S3 S5, J5 J7 J8 J11 J12 J14, N8, L1 L2 L3 L4 L12, M1
- **Judged by the model itself** (no code finding; labelled "model judgement"): T9 S4 S6 J15
- **Crawl report only:** N4 (navigation order; no safe typed action to move navigation elements).
- **Not covered, on purpose:** J6 (similarity definition is not specified for deterministic re-measurement), J13
  (synonym judgement), N5 (what counts as the same help-link position is ambiguous), and N9 (click-depth root is
  unspecified and the metric is report-only). Also not covered: metrics with no safe typed change (N1 to N3, N5 to
  N7, N9 to N11, J1 to J4, J9 to J10, T5, T10, T11, S7, L5 to L11, M2, M3), report-only T6, and the other
  metrics that need multiple pages but do not yet have a validated measurement.

## Crawl metrics

Pass `crawl=True` to opt in; crawling is disabled by default, and requires the analyzed page's absolute `url`.

```python
result = analyze_general(html, url="https://example.org/unit/page", crawl=True)
```

`crawl.py` only follows direct, unique links from the supplied page, and only to the same scheme, host, and port.
It samples at most six pages total (including the supplied page), uses a five-second timeout and a one-megabyte
response limit, accepts HTML only, does not follow redirects, sends no cookies or credentials, and rejects hosts
that resolve to non-public IP addresses. External links, static assets, and failed fetches are excluded; fetch
failures appear in `result["crawl"]["warnings"]`.

The only crawl measurements are J7 (the same link label points to multiple destinations), J8 (a destination's
label differs from the unit's most common label), and N4 (shared links in the first non-empty `<nav>` appear in a
different DOM order). J7/J8 can produce normal typed `set_link_text` recommendations on the analyzed page. Crawled pages
are evidence only and are never modified. N4 is returned as a report-only finding. Recommendations carry
`evidence_type="crawl"` and `evidence_websites`; their evidence text also lists the pages and websites used.

J6 and J13 need semantic judgements without a sufficiently defined scoring method; N5's "position" and N9's
click-depth root are not defined precisely enough for a safe measurement. They are intentionally deferred rather
than approximated. No crawl metric or crawl-derived evidence is sent to the model unless `crawl=True`.

## The guardrails

A proposal reaches a reviewer only if it passes all of these. They live in `guardrails.py`, one function each,
and every one has a test in `backend/tests/` that fails when the check is removed.

| # | Check | What it enforces |
|---|---|---|
| 1 | known_metric | The metric was measured on this page, or is a registered judgement metric |
| 2 | action_allowed | The typed change is one the policy allows for that metric |
| 3 | scope | It is aimed at the finding's own block (or a listed block for page-wide findings) |
| 4 | quotes_exact | Quoted text is copied exactly from the live block |
| 5 | facts_preserved | No number or name is lost or invented, no content dropped |
| 6 | rewrite_size | A rewrite is not a deletion, and T3/T4 rewrite the flagged sentence |
| 7 | label_quality | Link text, button labels, alt text and headings are specific and not on the stoplists |
| 8 | css_policy | CSS values sit inside the metric's threshold, only the metric's properties |
| 9 | rationale_numbers | Numbers in the rationale are copied from the findings |
| 10 | applies_cleanly | The renderer can apply it to the live page without skipping |
| 11 | improves_metric | The page is measured again with the same code: the finding is gone, or its score is lower |
| 12 | no_regression | Measured again: no other metric gets worse |
| 13 | plain_text_only | (schema) No HTML, closed action list, closed CSS list |
| 14 | budget | At most `A11Y_MAX_CHANGES` changes per page, and the policy's limit per metric, strongest first |
| 15 | no_overlap | No two changes on the same block, or on a block and its parent |

The evidence line on each card is built from the finding (metric, what was measured, the limit, the named source),
never written by the model, so it cannot cite something that was not measured.

If every proposal fails, the model is told why and asked again (`MODEL_MAX_RETRIES`). A proposal that fails is
reported in `guardrails.rejected` of the `/analyze` response with its reasons.

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `MODEL_MOCK`, `MODEL_BASE_URL`, `MODEL_NAME`, `MODEL_API_KEY` | | Same model settings as the rest of the backend |
| `A11Y_MAX_CHANGES` | 12 | Most changes proposed for one page |
| `A11Y_MAX_FINDINGS` | 20 | Most findings shown to the model |
| `A11Y_JUDGEMENT` | 1 | Set to 0 to skip the model's own judgement checks (shorter prompt, faster) |
| `A11Y_JUDGEMENT_BLOCKS` | 12 | Most prose blocks shown for judgement checks |

With `MODEL_MOCK=1` a rule-based stand-in (`standin.py`) answers in place of a model, so tests, CI and a demo without
a model run the same pipeline, guardrails included. It is not the product.

## Use it

```python
from genui import analyze_general, apply_general

result = analyze_general(html)               # page-only analysis; crawl is opt-in
result = analyze_general(html, url=url, crawl=True)  # includes the bounded crawl report
adapted = apply_general(html, accepted)      # {"adapted_html", "applied", "skipped", "skipped_reasons"}
```

Tests: `cd backend && MODEL_MOCK=1 uv run pytest tests`.

## Limits

- Layout metrics (L1 to L4, L12) need the rendered page (`render: true`, Playwright). CSS is checked against the
  threshold, not measured again, because there is no browser in the loop.
- The re-measure gate uses the same heuristics as the metrics (sentence splitting, conjunction list), so a fix is
  judged by the same rules that found the problem.
- Formula metrics (T1, T2, T7) must improve; they are not required to reach the target in one sentence.
- Meaning is protected by numbers, names and word coverage, not by understanding. A reviewer still approves each change.
