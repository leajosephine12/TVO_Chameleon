"""Shared data contracts.

`Recommendation` is the shared format agreed with the team (Interface 3 / the
"most important contract"). Everything the UI shows and every accept/deny/edit
decision is one of these objects.
"""
from typing import Literal

from pydantic import BaseModel, Field


class Recommendation(BaseModel):
    id: str = Field(description="Unique within one analysis, e.g. 'r12'")
    block_id: str = Field(description="Element id like 'p-4' ('<tag>-<n>' in document order), or 'page' for page-wide rules")
    type: str = Field(description="e.g. 'italic_text', 'typography', 'long_sentence'")
    original: str
    suggestion: str
    rationale: str
    evidence: str
    severity: Literal["low", "medium", "high"] = "medium"
    status: Literal["pending", "accepted", "denied", "edited"] = "pending"


class Guideline(BaseModel):
    id: str = Field(description="Stable id, e.g. 'L1.1.3'")
    level: int
    category: str
    title: str
    rule: str = Field(description="Plain-language rule from the research")
    params: dict = Field(default_factory=dict, description="Concrete values the engine applies")


class GuidelinesResponse(BaseModel):
    level: int
    guidelines: list[Guideline]


# returns a list of recommendation
class AnalyzeResult(BaseModel):
    level: int = 1
    recommendations: list[Recommendation]


class AdaptResult(BaseModel):
    adapted_html: str
    injected_css: str = Field(description="Stylesheet that was injected (empty if no page-wide rule was accepted)")
    applied: list[str] = Field(description="Recommendation ids that were applied")
    skipped: list[str] = Field(description="Accepted ids that could not be applied (block not found, unknown type)")
    contrast_ratio: float | None = Field(default=None, description="Set when the colour rule was applied")