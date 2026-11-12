"""Each guardrail, one at a time. A 'model' here is a function that returns a fixed reply, so every case is exact.

Needs the real textstat (the readability metrics): `uv run pytest` installs it.
"""
import json

import pytest
from genui.context import build_context
from genui.guardrails import check_proposal, select
from genui.measure import measure
from genui.planner import parse_proposals

LONG = (
    "Students compare different ways that consumers can get value for their money when spending, such as using "
    "reward programs, and they also learn how sales work in 2026 stores across Toronto, because prices change."
)
GOOD_REWRITE = (
    "Students compare ways that consumers get value for their money. They use reward programs. "
    "They also learn how sales work in 2026 stores across Toronto. Prices change."
)
PLANTS = (
    "Plants need light. They also need water and soil. Roots hold the plant in place. Leaves make food from the sun. "
    "Stems carry water up. Flowers make seeds for new plants. Some plants grow in the desert and need little water."
)
HTML = f"""<html><body>
<h1>Saving money</h1>
<p>{LONG}</p>
<p>{PLANTS}</p>
<p><a href="/guides/budget-basics.html">click here</a> to read more about budgets.</p>
<img src="/img/piggy-bank.jpg" alt="image">
<button>Submit</button>
<button><svg width="10" height="10"></svg></button>
<ul><li>One</li><li>Two</li><li>Three</li><li>Four</li><li>Five</li><li>Six</li><li>Seven</li><li>Eight</li><li>Nine</li></ul>
<video autoplay src="clip.mp4"></video>
</body></html>"""


def make_ctx(html=HTML, judgement=False):
    findings = measure(html, uncapped=True)
    ctx = build_context(html, findings, judgement=judgement)
    ctx.baseline = findings
    return ctx


def problems_for(ctx, metric, block, change, rationale="Fixes the finding.", severity="medium"):
    """Parse a proposal the way the planner does, then run every guardrail. Returns the problems (empty = accepted)."""
    reply = json.dumps({"proposals": [{"metric_id": metric, "block_id": block, "rationale": rationale,
                                       "severity": severity, "change": change}]})
    proposals, invalid = parse_proposals(reply, ctx)
    if invalid:
        return invalid[0]["reasons"]
    _, problems = check_proposal(proposals[0], ctx)
    return problems


@pytest.fixture(scope="module")
def ctx():
    return make_ctx()


def test_a_good_rewrite_passes_every_guardrail(ctx):
    assert problems_for(ctx, "T3", "p-1", {"action": "replace_text", "original": LONG, "value": GOOD_REWRITE}) == []


def test_1_unknown_metric_is_rejected(ctx):
    problems = problems_for(ctx, "T5", "p-1", {"action": "replace_text", "original": LONG, "value": GOOD_REWRITE})
    assert "not one of the findings" in problems[0]


def test_2_action_must_be_allowed_for_the_metric(ctx):
    problems = problems_for(ctx, "J5", "a-1", {"action": "replace_text", "original": "click here", "value": "Budget basics"})
    assert "may only be fixed with set_link_text" in problems[0]


def test_3_scope_is_the_findings_own_block(ctx):
    problems = problems_for(ctx, "T3", "p-2", {"action": "replace_text", "original": "Plants need light.", "value": "Plants need sun."})
    assert "has no finding in block p-2" in problems[0]


def test_3_unknown_block_is_rejected(ctx):
    assert "does not exist" in problems_for(ctx, "T3", "p-99", {"action": "replace_text", "original": "x", "value": "y"})[0]


def test_4_original_must_be_quoted_exactly(ctx):
    problems = problems_for(ctx, "T3", "p-1", {"action": "replace_text", "original": "Students study many things.", "value": "Short."})
    assert problems == ["'original' is not in block p-1; copy it exactly."]


def test_5_a_lost_number_or_name_is_rejected(ctx):
    no_number = GOOD_REWRITE.replace("2026 ", "")
    assert "lost facts" in problems_for(ctx, "T3", "p-1", {"action": "replace_text", "original": LONG, "value": no_number})[0]
    no_name = GOOD_REWRITE.replace(" across Toronto", "")
    assert "Toronto" in problems_for(ctx, "T3", "p-1", {"action": "replace_text", "original": LONG, "value": no_name})[0]


def test_5_an_invented_number_is_rejected(ctx):
    problems = problems_for(ctx, "T3", "p-1", {"action": "replace_text", "original": LONG, "value": GOOD_REWRITE + " Save 50 dollars."})
    assert "added number" in problems[0]


def test_5_a_list_that_drops_content_is_rejected():
    ctx = make_ctx("<p>Pack a coat, a hat, gloves, boots, a scarf and warm socks before you go outside today.</p>", judgement=True)
    ctx.judgement_blocks.append("p-1")
    problems = problems_for(ctx, "S4", "p-1", {"action": "text_to_list", "list_type": "bulleted", "items": ["A coat", "A hat"]})
    assert "dropped too much" in problems[0]


def test_6_a_rewrite_must_not_be_a_deletion(ctx):
    problems = problems_for(ctx, "T3", "p-1", {"action": "replace_text", "original": LONG, "value": "Students compare 2026 Toronto."})
    assert "much shorter" in problems[0]


def test_6_t3_must_quote_the_flagged_sentence(ctx):
    problems = problems_for(ctx, "T3", "p-1", {"action": "replace_text", "original": "Students compare different ways that consumers", "value": "Students compare ways that consumers"})
    assert problems == ["'original' must be exactly the flagged sentence."]


@pytest.mark.parametrize("metric,block,change,expected", [
    ("J5", "a-1", {"action": "set_link_text", "text": "Read more"}, "generic or unchanged"),
    ("J14", "button-1", {"action": "set_button_label", "label": "Send"}, "verb plus an object"),
    ("J12", "img-1", {"action": "set_alt_text", "alt": "image of a pig"}, "must describe the image"),
    ("J12", "img-1", {"action": "set_alt_text", "alt": "piggy-bank"}, "must describe the image"),
])
def test_7_labels_must_be_specific(ctx, metric, block, change, expected):
    assert expected in problems_for(ctx, metric, block, change)[0]


def test_7_good_labels_pass(ctx):
    assert problems_for(ctx, "J5", "a-1", {"action": "set_link_text", "text": "Read the budget guide"}) == []
    assert problems_for(ctx, "J14", "button-1", {"action": "set_button_label", "label": "Send application"}) == []
    assert problems_for(ctx, "J12", "img-1", {"action": "set_alt_text", "alt": "A pink piggy bank with coins"}) == []
    assert problems_for(ctx, "J11", "button-2", {"action": "add_button_label", "label": "Open menu"}) == []


def test_8_css_must_sit_inside_the_threshold():
    findings = [
        {"metric_id": "L3", "block_id": "p-1", "measured": {"font_size_px": 12.0}, "threshold": "t", "source": "s", "tier": "F", "detail": "d"},
        {"metric_id": "L2", "block_id": "p-1", "measured": {"line_height": 1.2, "text_align": "justify"}, "threshold": "t", "source": "s", "tier": "C", "detail": "d"},
        {"metric_id": "L1", "block_id": "p-1", "measured": {"line_length_chars": 120}, "threshold": "t", "source": "s", "tier": "C", "detail": "d"},
    ]
    html = "<p>Some text.</p>"
    ctx = build_context(html, findings, judgement=False)
    ctx.baseline = findings
    ok = lambda m, css: problems_for(ctx, m, "p-1", {"action": "set_style", "value": css})
    assert ok("L3", "font-size: 18px") == []
    assert "from 16px" in ok("L3", "font-size: 12px")[0]
    assert "may only set font-size" in ok("L3", "color: red")[0]
    assert ok("L2", "line-height: 1.6; text-align: left") == []
    assert ok("L2", "line-height: 1.2; text-align: left") == ["line-height must be a number from 1.5 to 3."]
    assert "justified" in ok("L2", "line-height: 1.6")[0]
    assert ok("L1", "max-width: 70ch") == []
    assert "between 30ch and 80ch" in ok("L1", "max-width: 120ch")[0]


def test_9_rationale_numbers_must_come_from_the_findings(ctx):
    change = {"action": "replace_text", "original": LONG, "value": GOOD_REWRITE}
    assert problems_for(ctx, "T3", "p-1", change, rationale="Sentence has 34 words.") == []
    assert "not in the findings" in problems_for(ctx, "T3", "p-1", change, rationale="Sentence has 99 words.")[0]


def test_10_a_change_the_page_cannot_take_is_rejected():
    html = '<p>Visit <a href="/x">the <b>big</b> garden</a> now and see the many plants that grow there every single day.</p>'
    ctx = make_ctx(html, judgement=True)
    ctx.judgement_blocks.append("p-1")
    problems = problems_for(ctx, "S4", "p-1", {"action": "text_to_list", "list_type": "bulleted",
                                                "items": ["Visit the big garden now", "See the many plants that grow there every single day"]})
    assert "could not be applied" in problems[0] and "inline formatting" in problems[0]


def test_11_the_page_is_measured_again_and_the_finding_must_be_gone(ctx):
    still_long = LONG.replace("can get", "can obtain")
    problems = problems_for(ctx, "T3", "p-1", {"action": "replace_text", "original": LONG, "value": still_long})
    assert "still flagged" in problems[0]


def test_11_a_split_that_leaves_a_long_part_is_rejected(ctx):
    sentences = PLANTS.split(". ")
    parts = [". ".join(sentences[:6]) + ".", sentences[6]]
    problems = problems_for(ctx, "S1", "p-2", {"action": "split_paragraph", "parts": parts})
    assert "still flagged" in problems[0]


def test_11_a_good_split_passes(ctx):
    sentences = PLANTS.split(". ")
    parts = [". ".join(sentences[:4]) + ".", ". ".join(sentences[4:])]
    assert problems_for(ctx, "S1", "p-2", {"action": "split_paragraph", "parts": parts}) == []


def test_12_a_fix_that_creates_a_new_problem_is_rejected():
    long_one = ("The class visited the farm and learned about many kinds of animals, plants, tools and seasons that "
                "farmers use in their daily work throughout the whole year.")
    html = f"<p>{long_one} Cows give milk. Hens lay eggs. Pigs eat corn. Sheep give wool.</p>"
    ctx = make_ctx(html)
    problems = problems_for(ctx, "T3", "p-1", {"action": "replace_text", "original": long_one, "value":
                            "The class visited the farm. They learned about many kinds of animals and plants. "
                            "They learned about tools and seasons. Farmers use them in their daily work throughout the whole year."})
    assert "makes S1 worse" in problems[0]


def test_13_html_in_a_value_is_rejected(ctx):
    problems = problems_for(ctx, "J5", "a-1", {"action": "set_link_text", "text": "<b>Read the guide</b>"})
    assert "plain text" in problems[0]


def test_13_an_action_outside_the_closed_list_is_rejected(ctx):
    problems = problems_for(ctx, "J5", "a-1", {"action": "delete_element"})
    assert "does not fit the typed change" in problems[0]


def _many_links(n):
    return "<html><body>" + "".join(f'<p><a href="/g/{i}">click here</a></p>' for i in range(n)) + "</body></html>"


def test_14_the_page_budget_keeps_the_strongest_and_reports_the_rest():
    ctx = make_ctx(_many_links(6))
    proposals = []
    for i in range(6):
        reply = json.dumps({"proposals": [{"metric_id": "J5", "block_id": f"a-{i + 1}", "rationale": "Link says nothing.",
                                           "severity": "low" if i < 2 else "high", "change": {"action": "set_link_text", "text": f"Read guide {i + 1}"}}]})
        p, _ = parse_proposals(reply, ctx)
        change, problems = check_proposal(p[0], ctx)
        assert problems == []
        proposals.append((p[0], change))
    kept, dropped = select(proposals, ctx, max_changes=10)
    assert len(kept) == 4  # the policy allows 4 J5 changes
    assert {p.block_id for p, _ in kept} == {"a-3", "a-4", "a-5", "a-6"}  # the 'high' ones win, low ones are dropped
    assert all("limit of 4 J5" in reason for _, reason in dropped)
    kept, dropped = select(proposals, ctx, max_changes=2)
    assert len(kept) == 2 and "page budget of 2" in dropped[0][1]


def test_15_two_changes_cannot_touch_the_same_block(ctx):
    pairs = []
    for metric in ("T3", "T4"):
        reply = json.dumps({"proposals": [{"metric_id": metric, "block_id": "p-1", "rationale": "Too long.", "severity": "medium",
                                           "change": {"action": "replace_text", "original": LONG, "value": GOOD_REWRITE}}]})
        p, _ = parse_proposals(reply, ctx)
        change, problems = check_proposal(p[0], ctx)
        assert problems == []
        pairs.append((p[0], change))
    kept, dropped = select(pairs, ctx)
    assert len(kept) == 1 and "already covers block p-1" in dropped[0][1]
