# Metrics → implementation map

Source: `docs/metrics.pdf` (TVO Chameleon Metrics — Beyond WCAG 2.0 AA).
Written as the design. What is implemented today is under "Status and next steps" at the end.

## The split

Every metric lands in exactly one of four buckets. Only bucket 1 (and the
code half of hybrids) goes into the MCP server; buckets 3–4 go into the
model prompt instead.

1. **CODE** — deterministic, no AI. Implemented as logic inside the existing
   MCP tools. These findings are *facts* the model receives as input.
2. **CODE+NLP** — deterministic but needs a local NLP model (spaCy parser,
   sentence embeddings). Still no LLM judgement; add after bucket 1 works.
3. **CRAWL** — needs multiple pages of the unit. Needs a `crawl_unit(urls)`
   tool later; out of scope for the single-page pipeline.
4. **MODEL** — real judgement. These are *not* coded. They become
   instructions in the backend's model-call prompts ("check whether each
   heading matches its section content"), optionally with code-extracted
   candidates attached.

## How findings reach the model

Already wired in the architecture — no new interface needed:

```
fetch_page ──> blocks ──────────────┐
analyze_text(blocks) ──> findings ──┤──> model call #1 (text recommendations)
structure_checks(url) ─> findings ──┤
run_axe(url) ──────────> violations ┤──> model call #2 (layout recommendations, + screenshot)
layout_metrics(url) ───> metrics ───┘
```

Each code finding carries `metric_id` (e.g. `"T3"`), the measured value, the
threshold, and the source citation from the PDF — so the model can copy them
straight into the recommendation contract's `rationale` and `evidence`
fields instead of inventing numbers. The system prompt tells the model:
*ground every recommendation in a finding; do not re-derive metrics.*

## Tool mapping (bucket 1 — implement in MCP server)

One new tool: `structure_checks(url)` — DOM-only checks (BeautifulSoup, no
browser). Everything else fits the existing four tools.

### `analyze_text(blocks)` — textstat + word lists, prose blocks only
| ID | Metric | How |
|---|---|---|
| T1 | Flesch-Kincaid grade | `textstat.flesch_kincaid_grade` per prose block; flag if differs from T2 by >2 grades |
| T2 | Dale-Chall / Spache | `textstat.dale_chall_readability_score` / `textstat.spache_readability` |
| T3 | Sentence length | sentence split, word count; flag >25 |
| T4 | Conjunctions per sentence | token match against conjunction list; flag >2 |
| T6 | Passive voice | be-verb + past-participle regex heuristic; report-only |
| T7 | Rare words | % tokens outside Dale-Chall 3000 list, proper nouns excluded (capitalised mid-sentence heuristic); flag >10% |
| S1 | Paragraph length | per block: flag >50 words or >5 sentences |

Prose-block filter: T-metrics run only on paragraph blocks — `fetch_page`
must tag each block with its element type so nav/list/table/heading blocks
are excluded (the PDF requires this for T1).

### `structure_checks(url)` — NEW tool, static DOM
| ID | Metric | How |
|---|---|---|
| S2 | Heading density | headings vs words; flag <1 per ~200 words |
| S3 | Section headings present | content section (e.g. `section`, long text run) without heading |
| S5 | List length | `ol/ul` with >7 `li`; `li` with >1 sentence |
| T8 | Unexplained abbreviations | all-caps token with no `<abbr>`, no parenthesised expansion at first use |
| J5 | Generic link text | link text in stoplist ('click here', 'more', 'here', 'read more') |
| J11 | Icon without text label | `a`/`button` whose only content is `img`/`svg` |
| J14 | Vague button label | stoplist half only ('Submit', 'OK', 'Go'); verb+object check stays bucket 4 |
| J12 | Alt text quality | heuristic half: alt empty / equals filename / 'image' / 'picture' |
| N1 | Location cue | `aria-current` or highlighted nav item present |
| N2 | Breadcrumb | `nav`+`ol`+`aria-current` present when URL depth >=3 |
| N3 | Multiple ways | count of {nav, search box, sitemap link, related links, ToC} >= 2 |
| N6 | Single navigation system | >1 primary nav landmark |
| N7 | In-site Back/Home | home link present on page |
| N8 | Dropdown depth/size | nested menu depth <=2, <=6 links per dropdown (static part) |
| L11 | Icons paired with text | `img`/`svg` without adjacent text sibling |
| M1 | Autoplay | `video[autoplay]`/`audio[autoplay]` without visible pause control (detection half) |
| M2 | Carousel | carousel markup heuristic: >5 slides, auto-advance attribute (detection half) |

### `layout_metrics(url)` — Playwright + `getComputedStyle`
| ID | Metric | How |
|---|---|---|
| L1 | Line length | rendered chars per line on prose elements; flag >80 |
| L2 | Line height / spacing / justify | computed `line-height` >=1.5, paragraph margin >=1.5x, `text-align: justify` flag |
| L3 | Body font size | computed `font-size` >=16px (>=18.7px target for younger children) |
| L6 | Reflow | set viewport 320px, detect horizontal scroll |
| L7 | Visual consistency | computed-style variance across same-role elements (all h2, buttons, links) |
| L8 | Visual density | interactive elements per viewport, text:whitespace ratio; report-only |
| L9/L10 | Fold checks | bounding boxes vs first viewport: links above fold, content visibly continues below (measurement half) |
| L12 | Fonts / colours | distinct font-families (flag >2) and colour count |

### `run_axe(url)` — axe-core, same Playwright session
| ID | Metric | How |
|---|---|---|
| — | WCAG baseline | default axe ruleset, as already planned |
| L4 | Target size | enable axe `target-size` rule (disabled by default — PDF notes this) |

**Dependency consequence:** `analyze_text` and `structure_checks` need no
browser (textstat, word lists, BeautifulSoup). `fetch_page`, `layout_metrics`,
`run_axe` share one Playwright instance — one render serves blocks,
screenshot, computed styles, and axe injection.

## Bucket 2 — CODE+NLP (deterministic, add later)

| ID | Metric | Needs |
|---|---|---|
| T5 | Nested/subordinate clauses | spaCy dependency parse; flag >=2 subordinate clauses |
| S7 | Front-loaded headings | POS tagging: key noun within first two words |
| J1 | Headings too similar | sentence-embedding cosine >0.8 or >=60% shared lemmas |
| J2 | Generic heading | stoplist (code now) + similarity to own section <0.3 |
| J3 | Heading vs section content | similarity <0.3 |
| J4 | Title vs h1 | similarity <0.5 |
| J9 | Nav labels too similar | pairwise cosine >0.8 |

These bolt onto `analyze_text`/`structure_checks` behind the same finding
format; a small local embedding model keeps them deterministic and cheap.

## Bucket 3 — CRAWL (needs multi-page tool, later)

J6 (link text vs destination), J7 (same label, different targets), J8
(different labels, same target), J13 (inconsistent terminology), N4
(consistent nav order), N5 (consistent help position), N9 (click depth,
report-only).

## Bucket 4 — MODEL judgement (prompt instructions, never coded)

T9 (jargon needing definition — code supplies word-list candidates), T10
(overall reading level verdict), S4 (inline enumeration should be a list),
S6 (one action per step), J10 (icon relates to label — vision call), J12/J14
judgement halves, J15 (ambiguous references), N10 (search spellcheck
quality), N11 (primary action identifiable — vision call), M2 judgement
half, L5 (non-text contrast — PDF: 0% automated), L9 ("key" links is a
judgement).

## Shared conventions (when implementing)

- **One finding schema everywhere:**
  `{metric_id, block_id|selector, measured, threshold, source, detail}` —
  slots directly into the recommendation contract's `rationale`/`evidence`.
- **One `THRESHOLDS` dict** in the MCP server, keyed by metric ID. The PDF's
  "Calibrate? = Yes" rows (T5, T7, T9, S4, S6, J1–J3, J9, J12–J15, N11, L12)
  are exactly the values teachers/testers will want to tune — never inline
  these numbers.
- **Tier (C/D/E/F) rides along** on each finding so the UI can prioritise.

## Status and next steps

Checked against the code on the `general_recommendations` branch, not against the plan above.
Of the 57 metrics in this map:

| Status | Count | Metrics |
|---|---|---|
| Measured by code, fix shown in the General tab | 21 | T1 T2 T3 T4 T7 T8, S1 S2 S3 S5, J5 J11 J12 J14, N8, L1 L2 L3 L4 L12, M1 |
| Judged by the model, shown in the General tab | 4 | T9 S4 S6 J15 |
| Measured, but no suggestion appears | 9 | T6, N1 N2 N3 N6 N7, L6 L11, M2 |
| Defined for the vision model, not used by the app | 3 | J10 N11 L5 |
| Not implemented | 20 | L7 L8 L9 L10 (bucket 1, deferred); T5 S7 J1 J2 J3 J4 J9 (bucket 2); J6 J7 J8 J13 N4 N5 N9 (bucket 3); T10 N10 (bucket 4) |

Partly done: L2 does not measure paragraph spacing, L12 does not count colours, S5 finds a list item
with several sentences but has no fix, N8 finds menu depth but has no fix, and J12 and J14 only have
their stoplist half.

L1, L2 and L3 are fixed by code (`backend/genui/computed.py`). The other fixes are written by the
model, so they need a real model: the `MODEL_MOCK=1` stand-in only splits sentences.

### Plan, in order of cost against what a reviewer gets

1. **Turn on a real model (no code).** Simpler wording (T1 T2 T7), abbreviations (T8) and the four
   judgement metrics (T9 S4 S6 J15) appear. Not yet run against a real model, so do this first.
2. **Show the nine measured findings as advice cards (small, client only).** T6, N1 N2 N3 N6 N7,
   L6, L11 and M2 are already in the `/analyze_general` response under `findings`. A read-only card
   with no Approve button surfaces them without inventing page changes. Open question: should the
   General tab show things a reviewer cannot approve?
3. **Vision judgements J10, N11, L5 (medium).** The registry (`VISION_JUDGEMENT`), the prompt and
   the screenshot exist in the older `/analyze` path. The work is sending the screenshot from the
   general flow. They have no automatic fix, so they are advice cards too.
4. **Finish the partly-done ones (small each).** Paragraph spacing for L2 and the colour count for
   L12 are a few lines of measuring in `rendered.py`. Leave L7 to L10 until a reviewer asks.
5. **Bucket 2: T5, S7, J1 to J4, J9 (large).** Before adding spaCy and an embedding model, try them
   as model judgement checks. If that is good enough, the dependencies are never needed.
6. **Bucket 3: J6 to J8, J13, N4, N5, N9 (largest).** Needs a crawler over a whole unit, and the app
   reviews one lesson at a time. Its own ticket (issue #17).

Left out on purpose: T10 (T1 and T2 already cover it per paragraph) and N10 (a captured page has no
working search).

Before steps 2, 3 and 5: they all add to `backend/genui`, and the `14-implement-level2` branch moves
files it imports (`adapted_renderer.py`, `adapted_ui_spec.py`). Settle that first.

### Future: model judgements that change structure, not only wording

On the captured TVO lessons, almost every suggestion is a text rewrite, because the lessons have none
of the structural problems code measures (long paragraphs, missing headings, vague links). The
judgements below would add structural suggestions. They are ordered by value for TVO lessons.

**Reusing page changes genui already has (small).** Each should need two entries: the instruction in
`accessibility_metrics/judgement.py` and a row in `backend/genui/policy.py`. Not yet tried, so "small"
is an estimate.

| New judgement | What the reviewer would see | Existing change it uses | Metric |
|---|---|---|---|
| A paragraph changes topic partway through | A new subheading where the topic shifts | `add_heading_before` | Extends S2, which today only counts headings per 200 words |
| A task paragraph tells the learner to do several things | The paragraph becomes numbered steps | `split_into_steps` | S6 exists but only looks at existing steps; this widens it to prose |
| A heading is vague or does not match its section ("Introduction", "More") | A specific heading | `replace_text` | J2 and J3 (bucket 2); the model can judge them instead of language tools |
| A heading buries its key word | The key word moved to the front | `replace_text` | S7 (bucket 2) |

The first two go beyond "this text is too long". TVO lessons are mostly activity instructions
("Brainstorm your ideas and record your thinking using a method of your choice"), so turning those into
steps and breaking sections by topic changes how the page is organised, not just its wording.

**Needing a new kind of page change (larger).**

- **Visible definition for a term.** `explain_term` only adds a hover tooltip, which touch-screen and
  keyboard users may never see. A definition in brackets or a small glossary would help more.
- **One question per list item.** Fixes the "two questions in one bullet" case found in Learning
  Activity 4 (S5 finds it today, with no fix).
- **Label next to an icon.** The most frequent unfixed finding on the captured lessons (L11, four or
  five per lesson). `add_button_label` only works on buttons and links.
- **Alt text judged from the image itself.** Several lesson images have empty alt text. The model
  would need to see the image, which genui does not send today.
