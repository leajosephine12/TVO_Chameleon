"""Call 3: generate_adapted_ui. Turns accepted recommendations into the adapted-page spec (placeholder schema).

Two implementations, same input and output:
- plain code (default): deterministic, never alters the accepted wording. RECOMMENDED.
- model (use_model=True): adapted_ui_model.py, kept so the team can compare. It must pass stricter checks.

Only recommendations with status 'accepted' or 'edited' are used (for 'edited', `suggestion` holds the user's own text).
Pending and denied ones are ignored, so it is safe to pass every recommendation.
"""
import re

from .adapted_ui_spec import AdaptedUIResult, AdaptedUISpec, Change, SkippedRecommendation, format_css, parse_css
from .schemas import Recommendation

APPROVED = ("accepted", "edited")


def _find(text: str, original: str) -> re.Match | None:
    """Locate `original` in `text`, ignoring differences in whitespace."""
    pattern = r"\s+".join(re.escape(word) for word in original.split())
    return re.search(pattern, text) if pattern else None


def select_usable(
    text_recs: list[Recommendation], layout_recs: list[Recommendation], blocks: list[dict] | None
) -> tuple[list[Recommendation], list[tuple[Recommendation, dict[str, str]]], list[SkippedRecommendation]]:
    """Keep approved recommendations that can be expressed in the spec; report the rest with a reason.

    Returns (text recs, (layout rec, parsed css) pairs, skipped).
    """
    block_text = {b["block_id"]: b["text"] for b in blocks or []}
    skipped: list[SkippedRecommendation] = []
    text_ok, layout_ok = [], []
    for r in (r for r in text_recs if r.status in APPROVED):
        if r.block_id not in block_text:
            skipped.append(SkippedRecommendation(id=r.id, reason=f"block '{r.block_id}' was not in the blocks you passed."))
        elif _find(block_text[r.block_id], r.original) is None:
            skipped.append(SkippedRecommendation(
                id=r.id, reason=f"the original text was not found in block '{r.block_id}' (the page may have changed)."))
        else:
            text_ok.append(r)
    for r in (r for r in layout_recs if r.status in APPROVED):
        try:
            layout_ok.append((r, parse_css(r.suggestion)))
        except ValueError as e:
            skipped.append(SkippedRecommendation(
                id=r.id,
                reason=f"{e} Structural changes (for example breaking text into steps) cannot be expressed in the placeholder spec."))
    return text_ok, layout_ok, skipped


def _generate_plain(
    text_recs: list[Recommendation], layout_recs: list[Recommendation], blocks: list[dict] | None
) -> AdaptedUIResult:
    text_ok, layout_ok, skipped = select_usable(text_recs, layout_recs, blocks)
    block_text = {b["block_id"]: b["text"] for b in blocks or []}

    new_text: dict[str, str] = {}
    for r in text_ok:
        current = new_text.get(r.block_id, block_text[r.block_id])
        match = _find(current, r.original)
        if match is None:  # an earlier accepted edit overlapped this one
            skipped.append(SkippedRecommendation(id=r.id, reason=f"another accepted edit already changed the text of '{r.original[:40]}...'."))
            continue
        new_text[r.block_id] = current[: match.start()] + r.suggestion + current[match.end() :]

    styles: dict[str, dict[str, str]] = {}
    for r, declarations in layout_ok:
        styles.setdefault(r.block_id, {}).update(declarations)  # later recommendations win per property

    changes = [Change(block_id=b, action="replace_text", value=t) for b, t in new_text.items()]
    changes += [Change(block_id=b, action="set_style", value=format_css(d)) for b, d in styles.items()]
    return AdaptedUIResult(spec=AdaptedUISpec(changes=changes), skipped=skipped)


def generate_adapted_ui(
    text_recs: list[Recommendation],
    layout_recs: list[Recommendation],
    blocks: list[dict] | None = None,
    *,
    use_model: bool = False,
    **model_options,
) -> AdaptedUIResult:
    """blocks: [{"block_id", "text"}], the same blocks the text recommendations were made from.

    Needed because replace_text carries the whole new block text, and one block can have several accepted edits.
    model_options (max_retries, config, transport, caller) only apply when use_model=True.
    """
    if use_model:
        from .adapted_ui_model import generate_adapted_ui_with_model  # imported here: avoids a circular import

        return generate_adapted_ui_with_model(text_recs, layout_recs, blocks, **model_options)
    if model_options:
        raise TypeError(f"{sorted(model_options)} only apply when use_model=True.")
    return _generate_plain(text_recs, layout_recs, blocks)
