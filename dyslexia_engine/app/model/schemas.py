"""
dyslexia_engine/model/schemas.py
Schemas for the model layer and the frontend/backend contract.

`Recommendation` and `AnalyzeResult` live in app/schemas.py. They are imported here,
not copied, so there is one definition of each.
"""
from pydantic import BaseModel, Field, model_validator

from ..schemas import AnalyzeResult, Recommendation

__all__ = [
    "Recommendation",
    "RecommendationList",
    "TextBlock",
    "AnalyzeRequest",
    "ApplyRequest",
    "AnalyzeResult",
    "SkippedRec",
    "Level2ApplyResult",
]


class RecommendationList(BaseModel):
    """What the model must return for calls 1 and 2 (JSON mode needs an object)."""

    recommendations: list[Recommendation]


class TextBlock(BaseModel):
    block_id: str
    text: str


def _check_unique_block_ids(blocks: list[TextBlock]) -> None:
    ids = [b.block_id for b in blocks]
    if len(ids) != len(set(ids)):
        raise ValueError("block_id values must be unique")


class AnalyzeRequest(BaseModel):
    level: int = 2
    blocks: list[TextBlock] = Field(min_length=1)
    enabled_rules: list[str] | None = None
    max_recommendations: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _unique_block_ids(self):
        _check_unique_block_ids(self.blocks)
        return self


class ApplyRequest(BaseModel):
    level: int = 2
    blocks: list[TextBlock] = Field(min_length=1)
    accepted: list[Recommendation]

    @model_validator(mode="after")
    def _unique_block_ids(self):
        _check_unique_block_ids(self.blocks)
        return self


class SkippedRec(BaseModel):
    id: str
    reason: str


class Level2ApplyResult(BaseModel):
    level: int = 2
    blocks: list[TextBlock]
    applied: list[str]
    skipped: list[SkippedRec]