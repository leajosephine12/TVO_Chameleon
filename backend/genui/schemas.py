"""What the model returns, and the recommendation the review UI shows.

The model proposes a typed page change (the GenUI spec in dyslexia_engine/app/model/adapted_ui_spec.py) for a metric.
Only replace_text is shaped differently here: the model rewrites just the flagged words, and the code builds the
block's full new text from that (so the model never has to retype the whole block).
"""
from typing import Annotated, Literal, Union

from app.model.adapted_ui_spec import (
    AddButtonLabel, AddHeadingBefore, AddSectionHeading, ExplainTerm, GroupMenuItems, PlainText, SetAltText,
    SetButtonLabel, SetLinkText, SetStyle, SplitIntoSteps, SplitList, SplitParagraph, StopAutoplay, TextToList,
)
from app.schemas import Recommendation
from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class RewriteText(BaseModel):
    """Replace only `original` (copied exactly from the block) with `value`. The rest of the block is untouched."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["replace_text"] = "replace_text"
    original: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    value: PlainText


ModelChange = Annotated[
    Union[
        RewriteText, SetStyle, TextToList, SplitIntoSteps, AddButtonLabel, GroupMenuItems, SetLinkText,
        SetButtonLabel, SetAltText, AddSectionHeading, SplitParagraph, ExplainTerm, AddHeadingBefore, StopAutoplay, SplitList,
    ],
    Field(discriminator="action"),
]


class Proposal(BaseModel):
    """One change the model proposes: which metric it fixes, where, how, and why in one short sentence."""

    metric_id: str
    block_id: str
    rationale: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    severity: Literal["low", "medium", "high"] = "medium"
    change: ModelChange


class A11yRecommendation(Recommendation):
    """The shared Recommendation, plus what the general-accessibility flow needs to preview and apply it.

    The extra fields are optional, so a dyslexia recommendation is still a valid A11yRecommendation.
    """

    title: str | None = None
    category: str | None = None  # reading | cognitive | wcag
    change: dict | None = Field(default=None, description="The typed page change (a GenUI spec change)")
    preview_html: str | None = Field(default=None, description="What replaces the block on the page, built by the renderer")
    preview_css: str | None = Field(default=None, description="CSS declarations for a set_style change")
