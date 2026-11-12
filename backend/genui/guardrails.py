"""Guardrails: every proposal the model makes must pass all of these before a reviewer ever sees it.

Each check takes one proposal (and the page context) and returns a list of problems; an empty list means it passed.
The checks are independent and listed in PROPOSAL_CHECKS, so the README can state exactly what is enforced:

     1 known_metric        the metric is one we measured on this page, or a registered judgement metric
     2 action_allowed      the typed change is one the policy allows for that metric
     3 scope               the change is aimed at the block the finding is about (or a listed anchor)
     4 quotes_exact        quoted text and expected_original are copied exactly from the live block
     5 facts_preserved     no number or name is lost or invented, and no content is dropped
     6 rewrite_size        a rewrite is not a deletion and not a rewrite of something else
     7 label_quality       labels, alt text and headings are specific, short and not on the stoplists
     8 css_policy          CSS values are inside the metric's threshold and only the metric's properties
     9 rationale_numbers   numbers in the rationale are copied from the findings, never calculated
    10 applies_cleanly     the renderer can apply it to the live page without skipping
    11 improves_metric     re-measure the changed page: the finding is gone (or its score lower)
    12 no_regression       re-measure: no other metric gets worse
    13 plain_text_only     (spec) no HTML, a closed list of actions, a closed list of CSS properties and values
    14 budget              at most N changes per page and M per metric, strongest first
    15 no_overlap          no two changes touch the same block, or a block and its parent

13 is enforced by the schema in dyslexia_engine/app/model/adapted_ui_spec.py; 14 and 15 work across proposals (select()).
"""
import re
from collections import Counter

from accessibility_metrics.thresholds import THRESHOLDS
from app.model.adapted_renderer import apply_adapted_spec
from app.model.adapted_ui import _find
from app.model.adapted_ui_spec import AdaptedUISpec, ReplaceText, parse_css
from app.model.guards import lost_facts, numbers_in
from pydantic import ValidationError

from .context import Context
from .measure import measure
from .policy import FORMULA_KEYS, MAX_CHANGES, POLICY, TIER_ORDER
from .schemas import Proposal, RewriteText

_SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}
_CSS_METRICS = {m for m, p in POLICY.items() if p.actions == ("set_style",)}
# Counts that must not go up after any change (formula scores are compared per block instead).
_REGRESSION_METRICS = ("T3", "T4", "S1", "S2", "S3", "S5", "T8", "J5", "J11", "J12", "J14", "N8", "M1")
_GENERIC_HEADINGS = {"introduction", "more", "overview", "section", "heading", "untitled", "part 1", "part 2"}
_ALT_PREFIXES = ("image of", "picture of", "photo of", "graphic of", "icon of")
_WORD = re.compile(r"[a-z0-9]+")


def _squash(text: str) -> str:
    return " ".join(text.split())


def _words(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def build_change(p: Proposal, ctx: Context):
    """The typed spec change this proposal stands for. For a rewrite the code builds the block's whole new text
    from the model's replacement of the flagged words, so the rest of the block cannot drift."""
    if p.block_id not in ctx.index and p.block_id != "page":
        raise ValueError(f"block {p.block_id} does not exist; use only the block_ids you were given.")
    if isinstance(p.change, RewriteText):
        text = ctx.text(p.block_id)
        match = _find(text, p.change.original)
        if match is None:
            raise ValueError(f"'original' is not in block {p.block_id}; copy it exactly.")
        return ReplaceText(block_id=p.block_id, value=text[: match.start()] + p.change.value + text[match.end():])
    return p.change


def _expected(change) -> str | None:
    return getattr(change, "expected_original", None)


def _items_text(change) -> str:
    """All the text a rebuilding change puts on the page."""
    if change.action == "text_to_list":
        return " ".join(change.items)
    if change.action == "split_into_steps":
        return " ".join([change.intro or "", *change.steps])
    if change.action == "split_paragraph":
        return " ".join(change.parts)
    return ""


# ---------- 1-3 what and where ----------

def known_metric(p: Proposal, ctx: Context, change) -> list[str]:
    metrics = {f["metric_id"] for f in ctx.findings} | set(ctx.judgement)
    if p.metric_id not in POLICY or p.metric_id not in metrics:
        return [f"metric '{p.metric_id}' is not one of the findings or judgement checks you were given ({', '.join(sorted(metrics))})."]
    return []


def action_allowed(p: Proposal, ctx: Context, change) -> list[str]:
    policy = POLICY.get(p.metric_id)
    if policy and p.change.action not in policy.actions:
        return [f"{p.metric_id} may only be fixed with {' or '.join(policy.actions)}, not {p.change.action}."]
    return []


def scope(p: Proposal, ctx: Context, change) -> list[str]:
    policy = POLICY.get(p.metric_id)
    if policy is None:
        return []
    block = p.block_id
    if policy.scope == "block":
        if p.metric_id == "L12":
            ok = block == "page"
        else:
            ok = block in {f["block_id"] for f in ctx.findings_for(p.metric_id)}
        return [] if ok else [f"{p.metric_id} has no finding in block {block}; use one of: {', '.join(sorted({f['block_id'] for f in ctx.findings_for(p.metric_id)})) or 'none'}."]
    if policy.scope == "anchor":
        return [] if block in ctx.anchors else [f"{p.metric_id} changes must point at one of the listed blocks, not {block}."]
    if policy.scope == "term":
        terms = [t for t, holders in ctx.terms.items() if block in holders]
        term = getattr(p.change, "term", None)
        return [] if term in terms else [f"{p.metric_id}: 'term' must be an unexplained abbreviation that appears in block {block}."]
    if policy.scope == "judgement":
        return [] if block in ctx.judgement_blocks else [f"{p.metric_id} judgements must point at one of the listed prose blocks, not {block}."]
    return []


# ---------- 4-6 the words ----------

def quotes_exact(p: Proposal, ctx: Context, change) -> list[str]:
    if p.block_id not in ctx.index:
        return [f"block {p.block_id} does not exist."]
    text = ctx.text(p.block_id)
    if isinstance(p.change, RewriteText):
        return [] if _find(text, p.change.original) else [f"'original' must be copied exactly from block {p.block_id}."]
    expected = _expected(change)
    if expected is not None and _squash(expected) != _squash(text):
        return [f"expected_original must be the block's text exactly: \"{text[:120]}\"."]
    term = getattr(change, "term", None)
    if term and not re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text):
        return [f"the term '{term}' is not in block {p.block_id}."]
    return []


def facts_preserved(p: Proposal, ctx: Context, change) -> list[str]:
    if isinstance(p.change, RewriteText):
        before, after = p.change.original, p.change.value
    elif _items_text(change):
        before, after = _expected(change), _items_text(change)
    else:
        return []
    problems = []
    lost = lost_facts(before, after)
    if lost:
        problems.append(f"the change lost facts from the original ({', '.join(lost)}). Keep every number and name.")
    invented = sorted(numbers_in(after) - numbers_in(before))
    if invented:
        problems.append(f"the change added number(s) {', '.join(invented)} that are not in the original.")
    if change.action in {"text_to_list", "split_into_steps"}:
        missing = _words(before) - _words(after)
        if len(missing) > 0.2 * max(len(_words(before)), 1):
            problems.append("the list or steps dropped too much of the original content. Keep every item.")
    return problems


def rewrite_size(p: Proposal, ctx: Context, change) -> list[str]:
    if not isinstance(p.change, RewriteText):
        return []
    original, value = _squash(p.change.original), _squash(p.change.value)
    problems = []
    if value == original:
        problems.append("the rewrite is identical to the original.")
    ratio = len(value) / max(len(original), 1)
    if not 0.4 <= ratio <= 1.8:
        problems.append(f"the rewrite is {'much shorter' if ratio < 0.4 else 'much longer'} than the original; keep the same content.")
    flagged = next((f for f in ctx.findings_for(p.metric_id) if f["block_id"] == p.block_id), None)
    sentence = (flagged or {}).get("measured", {}).get("sentence")
    if p.metric_id in {"T3", "T4"} and sentence and _squash(sentence) != original:
        problems.append("'original' must be exactly the flagged sentence.")
    return problems


# ---------- 7-9 labels, css, numbers ----------

def label_quality(p: Proposal, ctx: Context, change) -> list[str]:
    a = change.action
    problems = []
    if a == "set_link_text":
        label = change.text.lower().rstrip(".!")
        if label in THRESHOLDS["J5"]["stoplist"] or label == _squash(change.expected_original).lower():
            problems.append("the link text is still generic or unchanged.")
    elif a == "set_button_label":
        label = change.label.lower().rstrip(".!")
        if label in THRESHOLDS["J14"]["stoplist"] or len(label.split()) < 2:
            problems.append("a button label needs a verb plus an object, for example 'Send application'.")
    elif a == "set_alt_text":
        alt = change.alt.lower()
        file_stem = (ctx.blocks.get(p.block_id, {}).get("file_name") or "").rsplit(".", 1)[0].lower()
        if alt in THRESHOLDS["J12"]["stoplist"] or (file_stem and alt == file_stem) or alt.startswith(_ALT_PREFIXES):
            problems.append("alt text must describe the image, not name it ('image of', a filename or a generic word).")
        if len(change.alt) > 150:
            problems.append("alt text should be one short sentence (150 characters at most).")
    elif a in {"add_section_heading", "add_heading_before"}:
        words = change.heading.split()
        if change.heading.lower().strip(".:") in _GENERIC_HEADINGS or len(words) > 8:
            problems.append("a heading must name the topic in at most 8 words and not be generic.")
    elif a == "add_button_label":
        if change.label.lower() in THRESHOLDS["J14"]["stoplist"]:
            problems.append("the label must say what the button does.")
    elif a == "explain_term":
        if _squash(change.explanation).lower() == change.term.lower():
            problems.append("the explanation must say more than the term.")
    return problems


def _number(value: str, unit: str) -> float | None:
    m = re.fullmatch(rf"\s*(\d+(?:\.\d+)?)\s*{unit}\s*", value)
    return float(m.group(1)) if m else None


def css_policy(p: Proposal, ctx: Context, change) -> list[str]:
    if change.action != "set_style" or p.metric_id not in _CSS_METRICS:
        return []
    try:
        css = parse_css(change.value)
    except ValueError as e:
        return [str(e)]
    t = THRESHOLDS[p.metric_id]
    problems = []

    def need(prop: str) -> str | None:
        if prop not in css:
            problems.append(f"{p.metric_id} needs '{prop}'.")
            return None
        return css[prop]

    allowed = {"L1": {"max-width"}, "L2": {"line-height", "text-align", "margin-bottom", "margin-top", "margin"},
               "L3": {"font-size"}, "L4": {"min-width", "min-height", "padding"}, "L12": {"font-family"}}[p.metric_id]
    extra = sorted(set(css) - allowed)
    if extra:
        problems.append(f"{p.metric_id} may only set {', '.join(sorted(allowed))}, not {', '.join(extra)}.")
    if p.metric_id == "L1" and (v := need("max-width")):
        ch = _number(v, "ch")
        if ch is None or not 30 <= ch <= t["max_chars"]:
            problems.append(f"max-width must be between 30ch and {t['max_chars']}ch.")
    if p.metric_id == "L2":
        measured = next((f["measured"] for f in ctx.findings_for("L2") if f["block_id"] == p.block_id), {})
        if measured.get("text_align") == "justify" and "text-align" not in css:
            problems.append("the block is justified; set text-align to left.")
        if "text-align" in css and css["text-align"].lower() == "justify":
            problems.append("text-align must not be justify.")
        if "line-height" in css:
            lh = _number(css["line-height"], "")
            if lh is None or not t["min_line_height"] <= lh <= 3:
                problems.append(f"line-height must be a number from {t['min_line_height']} to 3.")
        elif measured.get("line_height", t["min_line_height"]) < t["min_line_height"]:
            problems.append(f"line-height must be at least {t['min_line_height']}.")
    if p.metric_id == "L3" and (v := need("font-size")):
        px = _number(v, "px")
        rem = _number(v, "r?em")
        size = px if px is not None else (rem * 16 if rem is not None else None)
        if size is None or not t["min_px"] <= size <= 48:
            problems.append(f"font-size must be from {t['min_px']:g}px to 48px.")
    if p.metric_id == "L4":
        for prop in ("min-width", "min-height"):
            if prop in css:
                px = _number(css[prop], "px")
                if px is None or not 24 <= px <= 96:
                    problems.append(f"{prop} must be from 24px to 96px.")
        if not {"min-width", "min-height", "padding"} & set(css):
            problems.append("L4 needs min-width, min-height or padding.")
    if p.metric_id == "L12" and (v := need("font-family")):
        if len([f for f in v.split(",") if f.strip()]) > t["max_font_families"]:
            problems.append(f"use at most {t['max_font_families']} font families.")
    return problems


def rationale_numbers(p: Proposal, ctx: Context, change) -> list[str]:
    allowed = numbers_in([f for f in ctx.findings_for(p.metric_id) if f["block_id"] == p.block_id])
    allowed |= numbers_in(THRESHOLDS.get(p.metric_id, {}).get("threshold", "")) | numbers_in(ctx.text(p.block_id) if p.block_id in ctx.index else "")
    unknown = sorted(numbers_in(p.rationale) - allowed)
    if unknown:
        return [f"the rationale uses number(s) {', '.join(unknown)} that are not in the findings. Copy numbers; never calculate."]
    return []


# ---------- 10-12 apply it, then measure again ----------

def _count(findings: list[dict], metric: str) -> int:
    return sum(1 for f in findings if f["metric_id"] == metric)


def _score(findings: list[dict], metric: str, block_id: str) -> float | None:
    key = FORMULA_KEYS[metric]
    values = [f["measured"][key] for f in findings if f["metric_id"] == metric and f["block_id"] == block_id and key in f["measured"]]
    return max(values) if values else None


def applies_cleanly(p: Proposal, ctx: Context, change) -> list[str]:
    """Apply the change to a copy of the live page. Stored on ctx so improves_metric reuses the result."""
    result = apply_adapted_spec(ctx.html, AdaptedUISpec(changes=[change]))
    if result.skipped:
        return [f"it could not be applied: {result.skipped[0]}."]
    ctx.applied_html = result.html
    return []


def improves_metric(p: Proposal, ctx: Context, change) -> list[str]:
    """The re-measure gate: measure the changed page with the same code that found the problem."""
    metric = p.metric_id
    if metric in _CSS_METRICS or POLICY[metric].scope == "judgement" or ctx.applied_html is None:
        return []  # CSS is checked by css_policy (no browser here); judgement metrics have no code measurement
    after = measure(ctx.applied_html, uncapped=True)
    before = ctx.baseline
    if metric in FORMULA_KEYS:
        was, now = _score(before, metric, p.block_id), _score(after, metric, p.block_id)
        if was is not None and now is not None and now >= was:
            return [f"{metric} score did not improve ({was} before, {now} after). Simplify more."]
    elif metric == "S2":
        was = next((f["measured"]["headings"] for f in before if f["metric_id"] == "S2"), None)
        now = next((f["measured"]["headings"] for f in after if f["metric_id"] == "S2"), None)
        if was is not None and now is not None and now <= was:
            return ["the page still has the same number of headings."]
    elif _count(after, metric) >= _count(before, metric):
        return [f"{metric} is still flagged after the change ({_count(after, metric)} finding(s), was {_count(before, metric)})."]
    return []


def no_regression(p: Proposal, ctx: Context, change) -> list[str]:
    if ctx.applied_html is None or p.metric_id in _CSS_METRICS:
        return []
    after = measure(ctx.applied_html, uncapped=True)
    worse = [m for m in _REGRESSION_METRICS if _count(after, m) > _count(ctx.baseline, m)]
    return [f"the change makes {', '.join(worse)} worse." ] if worse else []


# Order matters: cheap checks first; applies_cleanly must run before the two that re-measure.
PROPOSAL_CHECKS = (
    known_metric, action_allowed, scope, quotes_exact, facts_preserved, rewrite_size, label_quality, css_policy,
    rationale_numbers, applies_cleanly, improves_metric, no_regression,
)


def check_proposal(p: Proposal, ctx: Context) -> tuple[object | None, list[str]]:
    """Run every check. Returns (typed change, problems). Stops at the first failing check so the model gets one clear reason."""
    try:
        change = build_change(p, ctx)
    except (ValueError, ValidationError) as e:
        return None, [_first_line(e)]
    ctx.applied_html = None
    for check in PROPOSAL_CHECKS:
        problems = check(p, ctx, change)
        if problems:
            return None, problems
    return change, []


def _first_line(e: Exception) -> str:
    if isinstance(e, ValidationError):
        first = e.errors()[0]
        return f"{'.'.join(str(x) for x in first['loc'])}: {first['msg']}"
    return str(e)


# ---------- 14-15 across proposals ----------

def _overlaps(a, b) -> bool:
    """True when the two tags are the same element or one is inside the other (identity, not bs4's structural ==)."""
    return a is b or any(x is a for x in b.parents) or any(x is b for x in a.parents)


def select(accepted: list[tuple[Proposal, object]], ctx: Context, max_changes: int = MAX_CHANGES):
    """Apply the page budget: strongest first, at most max_changes in all, at most the policy's per metric,
    and no two changes on the same block or on a block and its parent. Returns (kept, dropped [(proposal, reason)])."""
    def strength(item):
        p = item[0]
        tier = next((f.get("tier", "F") for f in ctx.findings_for(p.metric_id)), "D")
        return (_SEVERITY_RANK[p.severity], TIER_ORDER.get(tier, 9))

    ordered = sorted(accepted, key=strength)  # sorted() is stable, so ties keep the model's order
    kept, dropped, per_metric, occupied = [], [], Counter(), []
    for p, change in ordered:
        tag = ctx.index[p.block_id] if p.block_id in ctx.index else ctx.soup
        if len(kept) >= max_changes:
            dropped.append((p, f"over the page budget of {max_changes} changes."))
        elif per_metric[p.metric_id] >= POLICY[p.metric_id].max_changes:
            dropped.append((p, f"over the limit of {POLICY[p.metric_id].max_changes} {p.metric_id} changes."))
        elif p.block_id != "page" and any(_overlaps(o, tag) for o in occupied):
            dropped.append((p, f"another change already covers block {p.block_id}."))
        else:
            kept.append((p, change))
            per_metric[p.metric_id] += 1
            if p.block_id != "page":
                occupied.append(tag)
    order = {id(p): i for i, (p, _) in enumerate(accepted)}
    kept.sort(key=lambda item: order[id(item[0])])
    return kept, dropped
