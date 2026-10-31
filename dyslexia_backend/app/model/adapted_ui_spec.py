"""PLACEHOLDER GenUI spec for call 3. The team has not given us the real schema.

>>> To swap in the real schema, change ONLY this file (and the two builders that fill it: adapted_ui.py and adapted_ui_model.py). <<<

Current placeholder:
    {"changes": [{"block_id": "p-4", "action": "replace_text|set_style", "value": "..."}]}

- replace_text: `value` is the new text of the whole block (plain text; the renderer must insert it as text, never as HTML).
- set_style:    `value` is CSS declarations, for example "line-height: 1.6; font-size: 18px". Only a safe list of properties is allowed.
"""
import re
from typing import Literal

from pydantic import BaseModel, Field, model_validator

ALLOWED_CSS_PROPERTIES = frozenset({
    "font-size", "font-family", "font-weight", "font-style", "line-height", "letter-spacing", "word-spacing",
    "max-width", "margin", "margin-top", "margin-bottom", "padding", "color", "background-color",
    "text-align", "text-decoration", "column-count",
})
_VALUE = re.compile(r"^[\w\s.,%#()'\"-]+$")
_FORBIDDEN_IN_VALUE = ("url(", "expression", "javascript", "@import", "var(")
_HTML_TAG = re.compile(r"<\s*/?\s*[a-zA-Z!]")


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


class Change(BaseModel):
    block_id: str = Field(min_length=1)
    action: Literal["replace_text", "set_style"]
    value: str

    @model_validator(mode="after")
    def _check_value(self) -> "Change":
        if self.action == "set_style":
            self.value = format_css(parse_css(self.value))
        else:
            if not self.value.strip():
                raise ValueError("replace_text needs a non-empty value.")
            if self.block_id == "page":
                raise ValueError("replace_text cannot target 'page'; it needs a real block_id.")
            if _HTML_TAG.search(self.value):
                raise ValueError("replace_text value must be plain text, not HTML.")
        return self


class AdaptedUISpec(BaseModel):
    changes: list[Change]


class SkippedRecommendation(BaseModel):
    id: str
    reason: str


class AdaptedUIResult(BaseModel):
    """The spec, plus accepted recommendations that could not be turned into a change (so nothing disappears silently)."""

    spec: AdaptedUISpec
    skipped: list[SkippedRecommendation] = []
