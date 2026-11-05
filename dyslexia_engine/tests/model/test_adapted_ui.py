import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.model.adapted_ui import generate_adapted_ui
from app.model.adapted_ui_spec import AdaptedUISpec, ReplaceText, parse_css
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


@pytest.mark.parametrize("metric,block,original,suggestion,action", [
    ("J5", {"block_id": "a-1", "text": "click here", "kind": "a"},
     "click here", "Read the course guide", "set_link_text"),
    ("J11", {"block_id": "button-1", "text": "", "kind": "button"},
     "", "Open menu", "add_button_label"),
    ("J12", {"block_id": "img-1", "text": "", "alt": "image", "kind": "img"},
     "image", "Students planting beans", "set_alt_text"),
    ("J14", {"block_id": "button-1", "text": "Submit", "kind": "button"},
     "Submit", "Submit application", "set_button_label"),
    ("S3", {"block_id": "section-1", "text": "Students plant beans.", "kind": "section"},
     "Students plant beans.", "Garden activities", "add_section_heading"),
])
def test_structural_metrics_map_to_typed_actions(metric, block, original, suggestion, action):
    rec = Recommendation(
        id="r20", block_id=block["block_id"], type=metric, original=original, suggestion=suggestion,
        rationale="Clearer control.", evidence=f"structure check / {metric}", severity="medium", status="accepted",
    )
    result = generate_adapted_ui([rec], [], [block])
    assert len(result.spec.changes) == 1 and result.spec.changes[0].action == action


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
        ReplaceText(block_id="p-1", value="Hi <script>alert(1)</script>")
    with pytest.raises(ValidationError):
        ReplaceText(block_id="page", value="text")
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


# ---- whole-word matching: "interest" must not be found inside "uninterested" ----

def _rec(id, block, original, suggestion, type="difficult_word", status="accepted"):
    return Recommendation(id=id, block_id=block, type=type, original=original, suggestion=suggestion,
                          rationale="r", evidence="e", status=status)


def test_a_word_edit_does_not_touch_the_same_letters_inside_another_word():
    blocks = [{"block_id": "p-1", "text": "Students were uninterested in interest rates."}]
    out = generate_adapted_ui([_rec("r1", "p-1", "interest", "extra money")], [], blocks)
    assert by_action(out, "replace_text")["p-1"] == "Students were uninterested in extra money rates."


def test_an_edit_whose_text_only_appears_inside_a_longer_word_is_skipped_with_a_reason():
    blocks = [{"block_id": "p-1", "text": "Students were uninterested in the lesson."}]
    out = generate_adapted_ui([_rec("r1", "p-1", "interest", "extra money")], [], blocks)
    assert out.spec.changes == [] and [s.id for s in out.skipped] == ["r1"]


def test_a_sentence_ending_in_a_full_stop_still_matches():
    blocks = [{"block_id": "p-1", "text": "Students compare ways to save money. They also save."}]
    out = generate_adapted_ui(
        [_rec("r1", "p-1", "Students compare ways to save money.", "Students look at ways to save money.", type="long_sentence")], [], blocks)
    assert by_action(out, "replace_text")["p-1"] == "Students look at ways to save money. They also save."


def test_a_phrase_at_the_very_end_of_the_text_still_matches():
    blocks = [{"block_id": "p-1", "text": "Students compare ways to save money. They also save"}]
    out = generate_adapted_ui([_rec("r1", "p-1", "They also save", "They spend less")], [], blocks)
    assert by_action(out, "replace_text")["p-1"] == "Students compare ways to save money. They spend less"


def test_whitespace_differences_still_match():
    blocks = [{"block_id": "p-1", "text": "Students   compare\nways to save money."}]
    out = generate_adapted_ui([_rec("r1", "p-1", "compare ways", "look at ways")], [], blocks)
    assert "look at ways" in by_action(out, "replace_text")["p-1"]


# ---- one change the spec rejects must not take the other accepted edits down with it ----

LONG_HEADING = "What interest means for people who borrow money from a bank"  # 58 characters, the limit is 40
SECTION = "Interest is the cost of borrowing money over time."
TWO_BLOCKS = [{"block_id": "p-1", "text": "Students compare ways to save money."}, {"block_id": "section-1", "text": SECTION}]


def test_a_too_long_heading_is_skipped_and_the_good_edit_survives():
    good = _rec("r1", "p-1", "compare ways", "look at ways", type="long_sentence")
    bad = _rec("r2", "section-1", SECTION, LONG_HEADING, type="S3")
    out = generate_adapted_ui([good, bad], [], TWO_BLOCKS)
    assert by_action(out, "replace_text") == {"p-1": "Students look at ways to save money."}
    assert [s.id for s in out.skipped] == ["r2"] and "40 characters" in out.skipped[0].reason


@pytest.mark.parametrize("metric,block,original", [("J14", "input-1", ""), ("J5", "a-1", ""), ("S3", "section-1", "")])
def test_structural_changes_with_no_original_are_skipped_not_a_crash(metric, block, original):
    out = generate_adapted_ui([_rec("r1", block, original, "Short label", type=metric)], [], [{"block_id": block, "text": ""}])
    assert out.spec.changes == [] and [s.id for s in out.skipped] == ["r1"]


def test_a_block_id_the_spec_does_not_accept_is_skipped_not_a_crash():
    blocks = [{"block_id": "my-widget-1", "text": "Some text here."}, {"block_id": "p-1", "text": "Other text."}]
    out = generate_adapted_ui([_rec("r1", "my-widget-1", "text here", "words here"), _rec("r2", "p-1", "Other", "Another")], [], blocks)
    assert by_action(out, "replace_text") == {"p-1": "Another text."}
    assert [s.id for s in out.skipped] == ["r1"]


def test_every_recommendation_behind_a_rejected_block_is_reported():
    blocks = [{"block_id": "p-1", "text": "One two three."}]
    recs = [_rec("r1", "p-1", "One", "<b>1</b>"), _rec("r2", "p-1", "three", "3")]   # the merged text contains markup
    out = generate_adapted_ui(recs, [], blocks)
    assert out.spec.changes == [] and sorted(s.id for s in out.skipped) == ["r1", "r2"]


def test_more_changes_than_a_spec_can_hold_are_reported_not_raised():
    blocks = [{"block_id": f"p-{i}", "text": f"Sentence number {i} here."} for i in range(1, 103)]
    recs = [_rec(f"r{i}", f"p-{i}", "Sentence", "Line") for i in range(1, 103)]
    out = generate_adapted_ui(recs, [], blocks)
    assert len(out.spec.changes) == 100 and [s.id for s in out.skipped] == ["r101", "r102"]


def test_a_text_recommendation_with_no_original_says_so():
    out = generate_adapted_ui([_rec("r1", "p-1", "", "New text", type="long_sentence")], [], [{"block_id": "p-1", "text": "Text."}])
    assert out.skipped[0].reason == "there is no original text to replace."
