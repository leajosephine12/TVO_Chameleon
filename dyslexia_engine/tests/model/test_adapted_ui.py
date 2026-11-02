import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.model.adapted_ui import generate_adapted_ui
from app.model.adapted_ui_spec import AdaptedUISpec, Change, parse_css
from app.model.mock import mock_response
from app.model.sample_data import SAMPLE_BLOCKS
from app.model.schemas import Recommendation

SAMPLES = Path(__file__).resolve().parents[2] / "samples"
P1, P2 = (b["text"] for b in SAMPLE_BLOCKS)


def mock_recs(task):
    return [Recommendation(**r) for r in json.loads(mock_response(task))["recommendations"]]


def accept(recs, status="accepted"):
    return [r.model_copy(update={"status": status}) for r in recs]


TEXT, LAYOUT = mock_recs("text_recs"), mock_recs("layout_recs")


def by_action(result, action):
    return {c.block_id: c.value for c in result.spec.changes if c.action == action}


# ---- text changes ----

def test_accepted_text_becomes_replace_text_with_the_whole_block():
    res = generate_adapted_ui(accept(TEXT), [], SAMPLE_BLOCKS)
    text = by_action(res, "replace_text")
    assert set(text) == {"p-1", "p-2"} and res.skipped == []
    assert TEXT[0].suggestion in text["p-1"] and TEXT[0].original not in text["p-1"]
    assert text["p-1"].startswith("Students will learn to create a plan")      # untouched parts survive
    assert text["p-1"].endswith("long-term financial planning.")
    assert text["p-2"] == P2.replace(TEXT[1].original, TEXT[1].suggestion)
    assert "40 minutes" in text["p-2"] and "Manitoulin Island" in text["p-2"]  # facts survive


def test_two_accepted_edits_in_one_block_are_merged_not_overwritten():
    second = Recommendation(
        id="r9", block_id="p-1", type="long_sentence", status="accepted", rationale="x", evidence="e",
        original="Students will learn to create a plan to reach financial goals and identify ways to maintain balanced budgets.",
        suggestion="Students will learn to make a plan. They will learn to keep a balanced budget.",
    )
    res = generate_adapted_ui(accept(TEXT[:1]) + [second], [], SAMPLE_BLOCKS)
    value = by_action(res, "replace_text")["p-1"]
    assert TEXT[0].suggestion in value and second.suggestion in value
    assert len([c for c in res.spec.changes if c.block_id == "p-1"]) == 1


def test_edited_recommendation_uses_the_users_own_text():
    mine = TEXT[0].model_copy(update={"status": "edited", "suggestion": "Students compare ways to save money."})
    assert "Students compare ways to save money." in by_action(generate_adapted_ui([mine], [], SAMPLE_BLOCKS), "replace_text")["p-1"]


def test_pending_and_denied_are_ignored():
    mixed = [TEXT[0].model_copy(update={"status": "denied"}), TEXT[1]]  # TEXT[1] is still pending
    res = generate_adapted_ui(mixed, [], SAMPLE_BLOCKS)
    assert res.spec.changes == [] and res.skipped == []


def test_missing_block_or_changed_text_is_skipped_with_a_reason_not_lost():
    changed = [{"block_id": "p-1", "text": "Completely different text now."}, SAMPLE_BLOCKS[1]]
    res = generate_adapted_ui(accept(TEXT), [], changed)
    assert [s.id for s in res.skipped] == ["r1"] and "not found" in res.skipped[0].reason
    assert set(by_action(res, "replace_text")) == {"p-2"}                          # the good one still applied
    assert generate_adapted_ui(accept(TEXT), [], None).skipped[0].reason.startswith("block 'p-1'")


# ---- style changes ----

def test_accepted_layout_becomes_set_style():
    res = generate_adapted_ui([], accept(LAYOUT), SAMPLE_BLOCKS)
    assert by_action(res, "set_style") == {"p-1": "line-height: 1.6"}


def test_styles_for_one_block_are_combined_and_later_wins():
    a = LAYOUT[0].model_copy(update={"id": "a", "status": "accepted", "suggestion": "line-height: 1.5; font-size: 16px"})
    b = LAYOUT[0].model_copy(update={"id": "b", "status": "accepted", "suggestion": "line-height: 1.6"})
    assert by_action(generate_adapted_ui([], [a, b]), "set_style") == {"p-1": "line-height: 1.6; font-size: 16px"}


def test_page_wide_style_is_allowed():
    rec = LAYOUT[0].model_copy(update={"block_id": "page", "status": "accepted"})
    assert by_action(generate_adapted_ui([], [rec]), "set_style") == {"page": "line-height: 1.6"}


def test_structural_suggestion_is_skipped_with_a_reason():
    steps = LAYOUT[0].model_copy(update={"id": "r7", "type": "break_into_steps", "status": "accepted",
                                         "suggestion": "Break this paragraph into numbered steps."})
    res = generate_adapted_ui([], [steps])
    assert res.spec.changes == [] and res.skipped[0].id == "r7" and "Structural" in res.skipped[0].reason


# ---- the spec itself ----

def test_output_is_exactly_the_placeholder_shape():
    out = generate_adapted_ui(accept(TEXT), accept(LAYOUT), SAMPLE_BLOCKS).spec.model_dump()
    assert set(out) == {"changes"} and all(set(c) == {"block_id", "action", "value"} for c in out["changes"])
    assert {c["action"] for c in out["changes"]} == {"replace_text", "set_style"}


def test_same_input_same_output():
    run = lambda: generate_adapted_ui(accept(TEXT), accept(LAYOUT), SAMPLE_BLOCKS).model_dump()
    assert run() == run()


@pytest.mark.parametrize("css", [
    "background: url(http://evil.test/x.png)", "color: red; behavior: url(x)", "font-size: expression(alert(1))",
    "line-height", "line-height:", "position: fixed", "color: red}</style><script>",
])
def test_unsafe_or_malformed_css_is_rejected(css):
    with pytest.raises(ValueError):
        parse_css(css)


def test_html_in_replace_text_is_rejected():
    with pytest.raises(ValidationError):
        Change(block_id="p-1", action="replace_text", value="Hi <script>alert(1)</script>")
    with pytest.raises(ValidationError):
        Change(block_id="page", action="replace_text", value="text")
    with pytest.raises(ValidationError):
        AdaptedUISpec.model_validate({"changes": [{"block_id": "p-1", "action": "delete", "value": "x"}]})


def test_saved_adapted_ui_samples_match_the_code():
    saved_in = json.loads((SAMPLES / "adapted_ui_input.json").read_text(encoding="utf-8"))
    saved_out = json.loads((SAMPLES / "adapted_ui_output.json").read_text(encoding="utf-8"))
    res = generate_adapted_ui(
        [Recommendation(**r) for r in saved_in["accepted_text_recommendations"]],
        [Recommendation(**r) for r in saved_in["accepted_layout_recommendations"]],
        saved_in["blocks"],
    )
    assert saved_out == res.spec.model_dump()
