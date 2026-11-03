"""Schemas for the model layer.

`Recommendation` is the team's shared format and lives in app/schemas.py. It is imported here,
not copied, so there is one definition. Importing it only needs pydantic (not fastmcp).
"""
from pydantic import BaseModel

from ..schemas import Recommendation

__all__ = ["Recommendation", "RecommendationList"]


class RecommendationList(BaseModel):
    """What the model must return for calls 1 and 2: an object (JSON mode needs an object, not a bare list)."""

    recommendations: list[Recommendation]
