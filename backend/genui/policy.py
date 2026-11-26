"""The guardrail policy for general accessibility: what the model may change, and how much.

This is policy, not content. It never says WHAT a heading, label or rewrite should be (the model decides that);
it says which metric may be fixed with which typed action, where, and how many times.

Numbers come from accessibility_engine THRESHOLDS (the metrics PDF), never from here.
"""
import os
from dataclasses import dataclass, replace

from accessibility_metrics.thresholds import THRESHOLDS

# A11Y_NO_LIMITS=1 lifts every budget in this file (changes per page and per metric, findings and blocks shown to
# the model, proposals checked), to see everything a page could get. Slow, and costly with a paid model.
NO_LIMITS = os.environ.get("A11Y_NO_LIMITS", "") == "1"
UNLIMITED = 10_000

# Whole page: how many things may change in one analysis. Reviewer attention is the budget.
MAX_CHANGES = UNLIMITED if NO_LIMITS else int(os.environ.get("A11Y_MAX_CHANGES", "12"))
# The model reads at most this many findings and this much page text per call.
MAX_FINDINGS_IN_PROMPT = UNLIMITED if NO_LIMITS else int(os.environ.get("A11Y_MAX_FINDINGS", "20"))
MAX_BLOCK_CHARS = 2000
MAX_ANCHORS = 40
MAX_JUDGEMENT_BLOCKS = UNLIMITED if NO_LIMITS else int(os.environ.get("A11Y_JUDGEMENT_BLOCKS", "12"))


@dataclass(frozen=True)
class MetricPolicy:
    title: str  # shown on the card
    category: str  # reading | cognitive | wcag (the review panel's filter)
    actions: tuple[str, ...]  # the typed changes allowed for this metric, nothing else
    max_changes: int  # per page
    scope: str  # block: the finding's own block | anchor: a listed block (page-wide finding) | term: a block holding the term | judgement: a listed prose block
    guidance: str  # one line of what a good fix looks like


def _t(metric_id: str, key: str):
    return THRESHOLDS[metric_id][key]


POLICY: dict[str, MetricPolicy] = {
    # --- text (the model rewrites only the flagged words; the numbers and names must survive) ---
    "T1": MetricPolicy("Reading level is high", "reading", ("replace_text",), 3, "block",
                       f"Rewrite the hardest sentence in shorter, simpler words. Target grade <= {_t('T1', 'max_grade')}."),
    "T2": MetricPolicy("Wording is hard", "reading", ("replace_text",), 3, "block",
                       "Swap the unfamiliar words in one sentence for common ones."),
    "T3": MetricPolicy("Sentence is long", "reading", ("replace_text",), 4, "block",
                       f"Cut the sentence into shorter ones of at most {_t('T3', 'max_words')} words (ideal {_t('T3', 'ideal')})."),
    "T4": MetricPolicy("Sentence chains clauses", "reading", ("replace_text",), 3, "block",
                       f"Split the sentence so each has at most {_t('T4', 'max_conjunctions')} conjunctions."),
    "T7": MetricPolicy("Rare words", "reading", ("replace_text",), 3, "block",
                       "Replace the rare words in one sentence with familiar ones; keep names."),
    "T8": MetricPolicy("Abbreviation is never explained", "reading", ("explain_term",), 3, "term",
                       "Give the abbreviation its full expansion as the explanation."),
    "T9": MetricPolicy("Term is not explained", "reading", ("explain_term",), 2, "judgement",
                       "Explain the term in a few plain words."),
    # --- structure and chunking ---
    "S1": MetricPolicy("Paragraph is long", "cognitive", ("split_paragraph", "text_to_list", "split_into_steps"), 3, "block",
                       f"Break it into parts of at most {_t('S1', 'max_words')} words and {_t('S1', 'max_sentences')} sentences, using the same words."),
    "S2": MetricPolicy("Too few headings", "cognitive", ("add_heading_before",), 3, "anchor",
                       f"Add a heading before a block where a new topic starts: about one per {_t('S2', 'words_per_heading')} words."),
    "S3": MetricPolicy("Section has no heading", "cognitive", ("add_section_heading",), 3, "block",
                       "Add a short heading that names what the section is about."),
    "S4": MetricPolicy("Items listed inline", "cognitive", ("text_to_list",), 2, "judgement",
                       "Turn the inline enumeration into a list; keep every item."),
    "S5": MetricPolicy("List is too long", "cognitive", ("split_list",), 2, "block",
                       f"Cut it into lists under short headings, at most {_t('S5', 'max_items')} items each."),
    "S6": MetricPolicy("Step packs several actions", "cognitive", ("split_into_steps",), 2, "judgement",
                       "Split into numbered steps with one action each."),
    # --- judgement of wording and labels ---
    "J5": MetricPolicy("Link text says nothing", "wcag", ("set_link_text",), 4, "block",
                       "Say where the link goes or what it does, in a few words."),
    "J11": MetricPolicy("Icon has no text", "wcag", ("add_button_label",), 4, "block",
                        "Add a short visible label for what the button does."),
    "J12": MetricPolicy("Alt text is missing or generic", "wcag", ("set_alt_text",), 4, "block",
                        "Describe what the image shows or does, in one short sentence."),
    "J14": MetricPolicy("Button label is vague", "wcag", ("set_button_label",), 4, "block",
                        "Use a verb plus an object, such as 'Send application'."),
    "J15": MetricPolicy("Unclear reference", "reading", ("replace_text",), 2, "judgement",
                        "Replace 'this', 'it' or 'the above' with what it refers to."),
    # --- navigation ---
    "N8": MetricPolicy("Menu is too large", "cognitive", ("split_list",), 2, "block",
                       f"Cut it into lists under short headings, at most {_t('N8', 'max_links')} links each."),
    # --- layout (CSS only, from the rendered page) ---
    "L1": MetricPolicy("Lines are too long", "reading", ("set_style",), 2, "block",
                       f"Limit the line length to at most {_t('L1', 'max_chars')} characters (ideal 50-75)."),
    "L2": MetricPolicy("Lines are cramped", "reading", ("set_style",), 3, "block",
                       f"Line height at least {_t('L2', 'min_line_height')}; no justified text."),
    "L3": MetricPolicy("Text is small", "reading", ("set_style",), 3, "block",
                       f"Body text at least {_t('L3', 'min_px'):g}px."),
    "L4": MetricPolicy("Target is small", "wcag", ("set_style",), 2, "block",
                       "Make the clickable area at least 24 by 24 pixels."),
    "L12": MetricPolicy("Too many fonts", "reading", ("set_style",), 1, "block",
                        f"Use at most {_t('L12', 'max_font_families')} font families."),
    # --- motion ---
    "M1": MetricPolicy("Media starts by itself", "wcag", ("stop_autoplay",), 2, "block",
                       "Stop autoplay and show the controls."),
}

if NO_LIMITS:
    POLICY = {metric: replace(policy, max_changes=UNLIMITED) for metric, policy in POLICY.items()}

# Metrics the model may raise itself (accessibility_engine.judgement.TEXT_JUDGEMENT), each labelled 'model judgement'.
JUDGEMENT_METRICS = tuple(m for m, p in POLICY.items() if p.scope == "judgement")

# Metrics measured by formula: a fix must lower the number (a sentence rewrite rarely reaches the target outright).
FORMULA_KEYS = {"T1": "flesch_kincaid_grade", "T2": "dale_chall", "T7": "rare_pct"}

# Report-only or unsupported metrics never reach the model.
TIER_ORDER = {"C": 0, "D": 1, "E": 2, "F": 3}
