"""General accessibility, model-driven: the model proposes typed page changes, guardrails check them, the renderer applies them."""
from .schemas import A11yRecommendation
from .service import analyze_general, apply_general

__all__ = ["A11yRecommendation", "analyze_general", "apply_general"]
