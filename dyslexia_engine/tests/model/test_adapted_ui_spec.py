"""The GenUI spec itself: the closed set of actions, their validation, and JSON round trips."""
import json

import pytest
from pydantic import ValidationError

from app.model.adapted_ui_spec import (
    AddButtonLabel, AddSectionHeading, AdaptedUISpec, GroupMenuItems, ReplaceText,
    SetAltText, SetButtonLabel, SetLinkText, SetStyle, SplitIntoSteps, TextToList,
)

VALID = [
    {"block_id": "p-1", "action": "replace_text", "value": "Short, plain text."},
    {"block_id": "page", "action": "set_style", "value": "line-height: 1.6"},
    {"block_id": "p-2", "action": "text_to_list", "list_type": "bulleted", "items": ["Apples", "Pears"],
     "expected_original": "Apples and pears."},
    {"block_id": "p-3", "action": "text_to_list", "list_type": "numbered", "items": ["One", "Two", "Three"],
     "expected_original": "One, two and three."},
    {"block_id": "p-4", "action": "split_into_steps", "steps": ["Open the app.", "Sign in."], "intro": "To start:",
     "expected_original": "Open the app, then sign in."},
    {"block_id": "button-2", "action": "add_button_label", "label": "Search", "placement": "below_icon"},
    {"block_id": "nav-1", "action": "group_menu_items", "groups": [
        {"label": "Learn", "item_ids": ["a-1", "a-2"]}, {"label": "Help", "item_ids": ["a-3"]}]},
    {"block_id": "a-4", "action": "set_link_text", "text": "Read the course guide", "expected_original": "click here"},
    {"block_id": "button-3", "action": "set_button_label", "label": "Submit application", "expected_original": "Submit"},
    {"block_id": "img-2", "action": "set_alt_text", "alt": "Students planting a garden", "expected_original": "image"},
    {"block_id": "section-2", "action": "add_section_heading", "heading": "Garden activities", "level": 2,
     "expected_original": "Students plant beans."},
]


def parse(*changes):
    return AdaptedUISpec.model_validate({"changes": list(changes)})


def rejected(change):
    with pytest.raises(ValidationError):
        parse(change)


# ---- valid operations ----

def test_every_action_parses_to_its_own_type():
    spec = parse(*VALID)
    assert [type(c) for c in spec.changes] == [
        ReplaceText, SetStyle, TextToList, TextToList, SplitIntoSteps, AddButtonLabel, GroupMenuItems,
        SetLinkText, SetButtonLabel, SetAltText, AddSectionHeading,
    ]


def test_whitespace_is_trimmed_and_defaults_are_filled():
    c = parse({"block_id": "button-1", "action": "add_button_label", "label": "  Menu  "}).changes[0]
    assert c.label == "Menu" and c.placement == "after_icon" and c.expected_original is None
    steps = parse({"block_id": "p-1", "action": "split_into_steps", "steps": [" a ", "b"],
                   "expected_original": "a then b"}).changes[0]
    assert steps.steps == ["a", "b"] and steps.intro is None


# ---- serialization / parsing ----

def test_json_round_trip_is_lossless():
    spec = parse(*VALID)
    again = AdaptedUISpec.model_validate_json(spec.model_dump_json())
    assert again == spec and json.loads(again.model_dump_json()) == spec.model_dump(mode="json")


def test_each_change_dumps_only_its_own_fields():
    keys = [set(c) for c in parse(*VALID).model_dump()["changes"]]
    assert keys[0] == keys[1] == {"block_id", "action", "value"}
    assert keys[2] == {"block_id", "action", "list_type", "items", "expected_original"}
    assert keys[6] == {"block_id", "action", "groups"}


def test_json_schema_is_a_discriminated_union_on_action():
    schema = AdaptedUISpec.model_json_schema()
    items = schema["properties"]["changes"]["items"]
    assert items["discriminator"]["propertyName"] == "action"
    assert set(items["discriminator"]["mapping"]) == {
        "replace_text", "set_style", "text_to_list", "split_into_steps", "add_button_label", "group_menu_items",
        "set_link_text", "set_button_label", "set_alt_text", "add_section_heading",
    }


def test_safe_renderer_id_shape_is_required():
    for unsafe in ("a.b:c", "x:hover", "5-5", "P-1", "p_1"):
        rejected({**VALID[0], "block_id": unsafe})


def test_rebuild_preconditions_and_collection_caps_are_required():
    for index in (2, 4):
        change = dict(VALID[index])
        change.pop("expected_original")
        rejected(change)
    rejected({"block_id": "nav-1", "action": "group_menu_items", "groups": [
        {"label": "A", "item_ids": [f"a-{i}" for i in range(21)]},
        {"label": "B", "item_ids": ["a-99"]},
    ]})
    with pytest.raises(ValidationError):
        AdaptedUISpec.model_validate({"changes": [VALID[0]] * 101})


def test_block_combination_is_explicit_and_order_independent():
    parse(VALID[0], {"block_id": "p-1", "action": "set_style", "value": "line-height: 1.6"})
    with pytest.raises(ValidationError):
        parse(VALID[0], {**VALID[2], "block_id": "p-1"})
    with pytest.raises(ValidationError):
        parse(
            {"block_id": "p-1", "action": "set_style", "value": "line-height: 1.6"},
            {"block_id": "p-1", "action": "set_style", "value": "font-size: 18px"},
        )


def test_structural_rewrites_must_preserve_numbers_and_names():
    rejected({
        "block_id": "p-1", "action": "text_to_list", "list_type": "bulleted",
        "items": ["The program starts soon.", "It is in Toronto."],
        "expected_original": "The program starts in 2026 in Toronto.",
    })
    rejected({
        "block_id": "p-1", "action": "split_into_steps", "steps": ["Open the form.", "Send it."],
        "expected_original": "Open the 2026 Toronto form, then send it.",
    })


# ---- backward compatibility ----

def test_old_placeholder_json_still_parses_and_dumps_the_same():
    old = {"changes": [{"block_id": "p-1", "action": "replace_text", "value": "Hi."},
                       {"block_id": "p-1", "action": "set_style", "value": "line-height:1.6;font-size: 18px"}]}
    out = parse(*old["changes"]).model_dump()
    assert out["changes"][0] == old["changes"][0]
    assert out["changes"][1] == {"block_id": "p-1", "action": "set_style", "value": "line-height: 1.6; font-size: 18px"}


def test_old_actions_still_ignore_unknown_keys_as_before():
    assert parse({"block_id": "p-1", "action": "replace_text", "value": "Hi.", "note": "x"}).model_dump()["changes"][0] == {
        "block_id": "p-1", "action": "replace_text", "value": "Hi."}


@pytest.mark.parametrize("change", [
    {"block_id": "p-1", "action": "set_style", "value": "background: url(http://evil.test/x.png)"},
    {"block_id": "p-1", "action": "set_style", "value": "position: fixed"},
    {"block_id": "p-1", "action": "replace_text", "value": "   "},
    {"block_id": "page", "action": "replace_text", "value": "text"},
])
def test_old_actions_keep_their_checks(change):
    rejected(change)


# ---- closed set: no arbitrary or destructive operations ----

@pytest.mark.parametrize("action", ["delete", "remove", "move", "insert_html", "set_attribute", "set_html", "", None])
def test_unknown_actions_are_rejected(action):
    rejected({"block_id": "p-1", "action": action, "value": "x"})


def test_structural_actions_reject_extra_keys():
    rejected({**VALID[2], "html": "<ul><li>a</li></ul>"})
    rejected({**VALID[5], "onclick": "alert(1)"})
    rejected({"block_id": "nav-1", "action": "group_menu_items",
              "groups": [{"label": "A", "item_ids": ["a-1"], "move_to": "x"}, {"label": "B", "item_ids": ["a-2"]}]})


# ---- unsafe HTML ----

@pytest.mark.parametrize("change", [
    {**VALID[2], "items": ["Fine", "<script>alert(1)</script>"]},
    {**VALID[2], "items": ["Fine", "<img src=x onerror=alert(1)>"]},
    {**VALID[4], "steps": ["Fine", "</p><p>"]},
    {**VALID[4], "intro": "<b>Start</b>"},
    {**VALID[5], "label": "<svg onload=alert(1)>"},
    {"block_id": "nav-1", "action": "group_menu_items",
     "groups": [{"label": "<i>A</i>", "item_ids": ["a-1"]}, {"label": "B", "item_ids": ["a-2"]}]},
])
def test_html_is_rejected_everywhere(change):
    rejected(change)


# ---- invalid input ----

@pytest.mark.parametrize("change", [
    {**VALID[2], "items": ["only one"]},                       # a list needs 2+ items
    {**VALID[2], "items": ["a", "  "]},                        # blank item
    {**VALID[2], "items": ["a", "b"] * 11},                    # more than 20
    {**VALID[2], "items": ["a", "x" * 501]},                   # item too long
    {**VALID[2], "list_type": "checklist"},                    # unknown list type
    {**VALID[2], "items": "a, b"},                             # not a list
    {**VALID[2], "items": ["a", 2]},                           # not strings
    {**VALID[2], "block_id": "page"},                          # structural changes need a real block
    {**VALID[2], "block_id": "p 1; drop"},                     # not an id
    {**VALID[2], "expected_original": "   "},                  # empty precondition
    {**VALID[4], "steps": []},
    {**VALID[5], "label": ""},
    {**VALID[5], "label": "x" * 41},                           # label too long for a button
    {**VALID[5], "label": "Two\nlines"},
    {**VALID[5], "placement": "replace_icon"},                 # the icon is never removed
    {**VALID[5], "placement": "inside_icon"},
    {"block_id": "nav-1", "action": "group_menu_items", "groups": [{"label": "All", "item_ids": ["a-1", "a-2"]}]},
    {"block_id": "nav-1", "action": "group_menu_items",
     "groups": [{"label": "A", "item_ids": ["a-1"]}, {"label": "B", "item_ids": []}]},
    {"block_id": "nav-1", "action": "group_menu_items",                                  # duplicated item
     "groups": [{"label": "A", "item_ids": ["a-1"]}, {"label": "B", "item_ids": ["a-1", "a-2"]}]},
    {"block_id": "nav-1", "action": "group_menu_items",                                  # the menu inside itself
     "groups": [{"label": "A", "item_ids": ["nav-1"]}, {"label": "B", "item_ids": ["a-2"]}]},
])
def test_invalid_parameters_are_rejected(change):
    rejected(change)


def test_one_bad_change_rejects_the_whole_spec():
    with pytest.raises(ValidationError):
        parse(VALID[0], {**VALID[2], "items": ["<b>x</b>", "y"]})


# ---- a lone '<' in prose is text, a real tag is not ----

from app.model.adapted_ui_spec import ReplaceText, TextToList  # noqa: E402


@pytest.mark.parametrize("text", ["Keep it if 5 <x litres.", "Is x < y and y > z?", "Use <3 as a heart.", "a<b", "Cost: 5 < 10"])
def test_prose_with_a_lone_less_than_sign_is_accepted(text):
    assert ReplaceText(block_id="p-1", value=text).value == text
    assert TextToList(block_id="p-1", list_type="bulleted", items=[text, "Second item"], expected_original=text + " Second item").items[0] == text


@pytest.mark.parametrize("text", [
    "<b>bold</b>", "Hi <script>alert(1)</script>", '<img src=x onerror="alert(1)">', "</p>", "x <!-- hidden --> y", "<!DOCTYPE html>",
])
def test_real_looking_markup_is_still_rejected(text):
    with pytest.raises(ValidationError):
        ReplaceText(block_id="p-1", value=text)
