"""GenUI spec for call 3: a closed list of safe, typed changes, each aimed at one block_id.

>>> To change the schema, change this file (and the two builders that fill it: adapted_ui.py and adapted_ui_model.py). <<<

    {"changes": [<change>, ...]}      every change has "block_id" and "action"; "action" picks the shape.

Content changes (unchanged from the first placeholder, same JSON shape):
- replace_text:     {"value"}  the new text of the whole block (plain text; the renderer inserts it as text, never as HTML).
- set_style:        {"value"}  CSS declarations, e.g. "line-height: 1.6; font-size: 18px". Only safe properties are allowed.

Structural changes (rebuild the content of ONE block in a fixed, renderer-defined way):
- text_to_list:     {"list_type": "bulleted|numbered", "items": [...], "expected_original"?}
- split_into_steps: {"steps": [...], "intro"?, "expected_original"?}
- add_button_label: {"label", "placement": "after_icon|below_icon", "expected_original"?}
- group_menu_items: {"groups": [{"label", "item_ids": [...]}, ...]}

There is deliberately no way to send HTML, run an arbitrary DOM operation, delete an element or move one.
expected_original is a precondition: the block's text as the backend saw it. If the live text differs
(ignoring whitespace), the renderer skips the change instead of applying it to stale content.
"""
import re
from typing import Annotated, Literal, Union

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, model_validator

ALLOWED_CSS_PROPERTIES = frozenset({
    "font-size", "font-family", "font-weight", "font-style", "line-height", "letter-spacing", "word-spacing",
    "max-width", "margin", "margin-top", "margin-bottom", "padding", "color", "background-color",
    "text-align", "text-decoration", "column-count",
})
_VALUE = re.compile(r"^[\w\s.,%#()'\"-]+$")
_FORBIDDEN_IN_VALUE = ("url(", "expression", "javascript", "@import", "var(")
_HTML_TAG = re.compile(r"<\s*/?\s*[a-zA-Z!]")

MAX_ITEMS = 20
MAX_ITEM_CHARS = 500
MAX_LABEL_CHARS = 40


def parse_css(css: str) -> dict[str, str]:
    """Parse 'prop: value; prop: value' into a dict, or raise ValueError. Unsafe or unknown properties are rejected."""
    declarations: dict[str, str] = {}
    for part in css.split(";"):
        if not part.strip():
            continue
        prop, sep, value = part.partition(":")
        prop, value = prop.strip().lower(), value.strip()
        if not sep or not value:
            raise ValueError(f"'{part.strip()}' is not a CSS declaration like 'line-height: 1.6'.")
        if prop not in ALLOWED_CSS_PROPERTIES:
            raise ValueError(f"CSS property '{prop}' is not allowed (allowed: {', '.join(sorted(ALLOWED_CSS_PROPERTIES))}).")
        if not _VALUE.match(value) or any(bad in value.lower() for bad in _FORBIDDEN_IN_VALUE):
            raise ValueError(f"CSS value '{value}' for '{prop}' is not allowed.")
        declarations[prop] = value
    if not declarations:
        raise ValueError("No CSS declarations found.")
    return declarations


def format_css(declarations: dict[str, str]) -> str:
    return "; ".join(f"{p}: {v}" for p, v in declarations.items())


def _plain(text: str) -> str:
    if _HTML_TAG.search(text):
        raise ValueError("must be plain text, not HTML.")
    return text


def _not_page(block_id: str) -> str:
    if block_id == "page":
        raise ValueError("structural changes need a real block_id, not 'page'.")
    return block_id


# Stripped, non-empty, plain text.
PlainText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_ITEM_CHARS), AfterValidator(_plain)]
# A short one-line label (no line breaks).
Label = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_LABEL_CHARS, pattern=r"^[^\r\n]+$"),
    AfterValidator(_plain),
]
# Ids look like 'p-4' / 'li-12'. 'page' is a real block_id only for set_style.
BlockId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][\w.:-]{0,127}$")]
TargetId = Annotated[BlockId, AfterValidator(_not_page)]
Original = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class _Structural(BaseModel):
    model_config = ConfigDict(extra="forbid")  # only the fields of the chosen action


class ReplaceText(BaseModel):
    block_id: str = Field(min_length=1)
    action: Literal["replace_text"] = "replace_text"
    value: str

    @model_validator(mode="after")
    def _check_value(self) -> "ReplaceText":
        if not self.value.strip():
            raise ValueError("replace_text needs a non-empty value.")
        if self.block_id == "page":
            raise ValueError("replace_text cannot target 'page'; it needs a real block_id.")
        if _HTML_TAG.search(self.value):
            raise ValueError("replace_text value must be plain text, not HTML.")
        return self


class SetStyle(BaseModel):
    block_id: str = Field(min_length=1)
    action: Literal["set_style"] = "set_style"
    value: str

    @model_validator(mode="after")
    def _check_value(self) -> "SetStyle":
        self.value = format_css(parse_css(self.value))
        return self


class TextToList(_Structural):
    """Show the block's content as a list. The renderer puts each item in as text."""

    block_id: TargetId
    action: Literal["text_to_list"] = "text_to_list"
    list_type: Literal["bulleted", "numbered"]
    items: list[PlainText] = Field(min_length=2, max_length=MAX_ITEMS)
    expected_original: Original | None = None


class SplitIntoSteps(_Structural):
    """Show the block's content as numbered steps, with an optional plain-text line before them."""

    block_id: TargetId
    action: Literal["split_into_steps"] = "split_into_steps"
    steps: list[PlainText] = Field(min_length=2, max_length=MAX_ITEMS)
    intro: PlainText | None = None
    expected_original: Original | None = None


class AddButtonLabel(_Structural):
    """Add a visible text label next to an icon-only button. The button and what it does are unchanged."""

    block_id: TargetId
    action: Literal["add_button_label"] = "add_button_label"
    label: Label
    placement: Literal["after_icon", "below_icon"] = "after_icon"
    expected_original: Original | None = None


class MenuGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: Label
    item_ids: list[TargetId] = Field(min_length=1)


class GroupMenuItems(_Structural):
    """Add group headings inside a menu. Items are never moved, reordered or removed:
    all groups' item_ids, in order, must equal the menu's current items, or the renderer skips the change."""

    block_id: TargetId
    action: Literal["group_menu_items"] = "group_menu_items"
    groups: list[MenuGroup] = Field(min_length=2, max_length=MAX_ITEMS)

    @model_validator(mode="after")
    def _check_items(self) -> "GroupMenuItems":
        ids = [i for g in self.groups for i in g.item_ids]
        if len(ids) != len(set(ids)):
            raise ValueError("each menu item may appear in only one group, once.")
        if self.block_id in ids:
            raise ValueError("the menu itself cannot be one of its items.")
        return self


Change = Annotated[
    Union[ReplaceText, SetStyle, TextToList, SplitIntoSteps, AddButtonLabel, GroupMenuItems],
    Field(discriminator="action"),
]
CONTENT_ACTIONS = ("replace_text", "set_style")
STRUCTURAL_ACTIONS = ("text_to_list", "split_into_steps", "add_button_label", "group_menu_items")


class AdaptedUISpec(BaseModel):
    changes: list[Change]


class SkippedRecommendation(BaseModel):
    id: str
    reason: str


class AdaptedUIResult(BaseModel):
    """The spec, plus accepted recommendations that could not be turned into a change (so nothing disappears silently)."""

    spec: AdaptedUISpec
    skipped: list[SkippedRecommendation] = []
