# Metrics → implementation map

Source: `docs/metrics.pdf` (TVO Chameleon Metrics — Beyond WCAG 2.0 AA).
The map below distinguishes existing measurements from planned work; crawl implementation status is in Bucket 3.

## The split

Every metric lands in exactly one of four buckets. Only bucket 1 (and the
code half of hybrids) goes into the MCP server; buckets 3–4 go into the
model prompt instead.

1. **CODE** — deterministic, no AI. Implemented as logic inside the existing
   MCP tools. These findings are *facts* the model receives as input.
2. **CODE+NLP** — deterministic but needs a local NLP model (spaCy parser,
   sentence embeddings). Still no LLM judgement; add after bucket 1 works.
3. **CRAWL** — needs multiple pages of the unit. The GenUI library has an
   opt-in bounded same-origin crawl for J7/J8 and a report-only N4 comparison.
   Semantic or underspecified metrics stay deferred; see `backend/genui/README.md`.
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

## Bucket 3 — CRAWL

`backend/genui/crawl.py` starts with the analyzed page and samples up to five
direct, unique, same-origin HTML links. The page selection is intentionally
bounded; crawled pages inform recommendations but are never modified.

| ID | Status | Measurement / action |
|---|---|---|
| J7 | Implemented | Exact repeated link label with multiple destinations; the model may propose a typed `set_link_text` change on the analyzed page. |
| J8 | Implemented | A link to a shared destination whose label differs from the unique most-common label in the sample; the model may normalize that page's link label with `set_link_text`. Ties are not proposed. |
| N4 | Report-only | Compare the relative DOM order of shared links in the first navigation landmark; no element-moving action is supported. |
| J6 | Deferred | The metric's `< 0.3` similarity threshold does not define a similarity algorithm; no reproducible re-measure gate yet. |
| J13 | Deferred | Inconsistent terminology requires synonym/concept judgement; no deterministic candidate rule is defined. |
| N5 | Deferred | "Same place" for help/contact links does not define DOM, landmark, or visual position. |
| N9 | Deferred | Click depth is report-only, and the metrics document does not specify the root page from which depth is measured. |

The crawl is opt-in (`analyze_general(..., crawl=True)`), same scheme/host/port
only, capped at six pages including the seed, and uses bounded HTML-only
requests. Crawl findings retain the metric source, sampled page URLs and website
origins. J7/J8 recommendations are explicitly marked as crawl evidence; N4
findings carry no suggested change.

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
