"""Call 3: generate_adapted_ui. Plain code, no model.

Turns the accepted text and layout recommendations into the adapted-page spec (placeholder schema, see
adapted_ui_spec.py). Same input always gives the same output, and the accepted wording is never altered.

Only recommendations with status 'accepted' or 'edited' are used (for 'edited', `suggestion` holds the user's own text).
Pending and denied ones are ignored, so it is safe to pass every recommendation.
"""
import re

from .adapted_ui_spec import AdaptedUIResult, AdaptedUISpec, Change, SkippedRecommendation, format_css, parse_css
from .schemas import Recommendation

APPROVED = ("accepted", "edited")


def _replace_once(text: str, original: str, replacement: str) -> str | None:
    """Replace the first occurrence of `original` (whitespace-insensitive). None if it is not there."""
    pattern = r"\s+".join(re.escape(word) for word in original.split())
    if not pattern:
        return None
    match = re.search(pattern, text)
    return None if match is None else text[: match.start()] + replacement + text[match.end() :]


def generate_adapted_ui(
    text_recs: list[Recommendation],
    layout_recs: list[Recommendation],
    blocks: list[dict] | None = None,
) -> AdaptedUIResult:
    """blocks: [{"block_id", "text"}], the same blocks the text recommendations were made from.

    Needed because replace_text carries the whole new block text, and one block can have several accepted edits.
    """
    block_text = {b["block_id"]: b["text"] for b in blocks or []}
    skipped: list[SkippedRecommendation] = []

    def skip(rec: Recommendation, reason: str) -> None:
        skipped.append(SkippedRecommendation(id=rec.id, reason=reason))

    new_text: dict[str, str] = {}
    for r in (r for r in text_recs if r.status in APPROVED):
        if r.block_id not in block_text:
            skip(r, f"block '{r.block_id}' was not in the blocks you passed.")
            continue
        updated = _replace_once(new_text.get(r.block_id, block_text[r.block_id]), r.original, r.suggestion)
        if updated is None:
            skip(r, f"the original text was not found in block '{r.block_id}' (it may have changed, or another edit overlaps it).")
        else:
            new_text[r.block_id] = updated

    styles: dict[str, dict[str, str]] = {}
    for r in (r for r in layout_recs if r.status in APPROVED):
        try:
            declarations = parse_css(r.suggestion)
        except ValueError as e:
            skip(r, f"{e} Structural changes (for example breaking text into steps) cannot be expressed in the placeholder spec.")
            continue
        styles.setdefault(r.block_id, {}).update(declarations)  # later recommendations win per property

    changes = [Change(block_id=b, action="replace_text", value=t) for b, t in new_text.items()]
    changes += [Change(block_id=b, action="set_style", value=format_css(d)) for b, d in styles.items()]
    return AdaptedUIResult(spec=AdaptedUISpec(changes=changes), skipped=skipped)
