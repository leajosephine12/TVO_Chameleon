"""
dyslexia_engine/app/adaptation_engine.py

Orchestrator: the one entry point for analysing and adapting a page, whatever the level.
The API and the tests call these two functions and nothing deeper.

  analyze(level, html=..., blocks=..., enabled_rules=..., max_recommendations=...) -> AnalyzeResult
  apply(level, html=..., blocks=..., accepted=[...])                              -> AdaptResult | Level2ApplyResult

Level 1 (representation / CSS)  works on an HTML string.  Block ids are "<tag>-<n>", e.g. "p-4".
Level 2 (plain-language text)   works on text blocks: [{"block_id", "text"}].
Send the same html / blocks to analyze and apply.
"""
from .levels.level1_representation import analyze_level1, apply_level1
from .levels.level2_plain_text import analyze_level2, apply_level2
from .model.schemas import Level2ApplyResult
from .schemas import AdaptResult, AnalyzeResult, Recommendation

SUPPORTED_LEVELS = (1, 2)

def _check_level(level: int) -> None:
    if level not in SUPPORTED_LEVELS:
        raise ValueError(f"Unsupported level {level!r}. Supported: {list(SUPPORTED_LEVELS)}.")


def analyze(
    level: int,
    *,
    html: str | None = None,
    blocks: list[dict] | None = None,
    enabled_rules: set[str] | list[str] | None = None,
    max_recommendations: int | None = None,
) -> AnalyzeResult:
    """Analyse the content and return pending recommendations. Nothing is changed."""
    _check_level(level)
    if level == 1:
        if html is None:
            raise ValueError("Level 1 needs `html`.")
        return AnalyzeResult(level=1, recommendations=analyze_level1(html), findings=None)

    if not blocks:
        raise ValueError("Level 2 needs `blocks`.")
    return analyze_level2(
        blocks,
        set(enabled_rules) if enabled_rules else None,
        max_recommendations,
    )


def apply(
    level: int,
    *,
    accepted: list[Recommendation],
    html: str | None = None,
    blocks: list[dict] | None = None,
) -> AdaptResult | Level2ApplyResult:
    """Apply only the recommendations the user accepted."""
    _check_level(level)
    if level == 1:
        if html is None:
            raise ValueError("Level 1 needs `html`.")
        # apply_level1 only acts on status accepted/edited. Everything in `accepted` was accepted
        # by the user, so a card still marked "pending" counts as accepted. Denied stays denied.
        recs = [r.model_copy(update={"status": "accepted"}) if r.status == "pending" else r for r in accepted]
        return apply_level1(html, recs)

    if not blocks:
        raise ValueError("Level 2 needs `blocks`.")
    return apply_level2(blocks, accepted)