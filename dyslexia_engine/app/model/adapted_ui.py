"""Call 3: generate_adapted_ui. Turns accepted recommendations into the adapted-page spec (adapted_ui_spec.py).

Two implementations, same input and output:
- plain code (default): deterministic, never alters the accepted wording. RECOMMENDED.
- model (use_model=True): adapted_ui_model.py, kept so the team can compare. It must pass stricter checks.

Only recommendations with status 'accepted' or 'edited' are used (for 'edited', `suggestion` holds the user's own text).
Pending and denied ones are ignored, so it is safe to pass every recommendation.
"""
import re

from pydantic import ValidationError

from .adapted_ui_spec import (
    MAX_CHANGES, AddButtonLabel, AddSectionHeading, AdaptedUIResult, AdaptedUISpec, ReplaceText,
    SetAltText, SetButtonLabel, SetLinkText, SetStyle, SkippedRecommendation,
    format_css, parse_css,
)
from .schemas import Recommendation

APPROVED = ("accepted", "edited")
STRUCTURAL_METRIC_IDS = frozenset({"J5", "J11", "J12", "J14", "S3"})
STRUCTURAL_METRICS_REQUIRING_ORIGINAL = frozenset({"J5", "J14", "S3"})


def _find(text: str, original: str) -> re.Match | None:
    """Locate `original` in `text`, ignoring differences in whitespace.

    Whole words only: "interest" must not match inside "uninterested". The boundary is only required on a side
    where `original` starts or ends with a word character, so a sentence ending in "." still matches.
    """
    words = original.split()
    if not words:
        return None
    pattern = r"\s+".join(re.escape(word) for word in words)
    if re.match(r"\w", words[0]):
        pattern = r"(?<!\w)" + pattern
    if re.search(r"\w$", words[-1]):
        pattern += r"(?!\w)"
    return re.search(pattern, text)


def select_usable(
    text_recs: list[Recommendation], layout_recs: list[Recommendation], blocks: list[dict] | None
) -> tuple[list[Recommendation], list[tuple[Recommendation, dict[str, str]]], list[SkippedRecommendation]]:
    """Keep approved recommendations that can be expressed in the spec; report the rest with a reason.

    Returns (text recs, (layout rec, parsed css) pairs, skipped).
    """
    block_data = {b["block_id"]: b for b in blocks or []}
    block_text = {block_id: b.get("alt", "") if b.get("kind") == "img" else b.get("text", "")
                  for block_id, b in block_data.items()}
    skipped: list[SkippedRecommendation] = []
    text_ok, layout_ok = [], []
    for r in (r for r in text_recs if r.status in APPROVED):
        metric = r.type.upper()
        if r.block_id not in block_text:
            skipped.append(SkippedRecommendation(
                id=r.id, reason=f"block '{r.block_id}' was not in the blocks you passed."))
            continue
        current = block_text[r.block_id]
        if metric in STRUCTURAL_METRICS_REQUIRING_ORIGINAL and not r.original.strip():
            skipped.append(SkippedRecommendation(
                id=r.id, reason=f"{metric} needs the original text so stale content is not changed."))
        elif metric in STRUCTURAL_METRIC_IDS and not r.original.strip() and current.strip():
            skipped.append(SkippedRecommendation(
                id=r.id, reason=f"block '{r.block_id}' is no longer empty (the page may have changed)."))
        elif r.original and _find(current, r.original) is None:
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
                reason=f"{e} Structural changes (for example breaking text into steps) are not generated from recommendations yet."))
    return text_ok, layout_ok, skipped


def _why(error: ValidationError) -> str:
    """One readable sentence for the first thing the spec rejected."""
    first = error.errors()[0]
    where = ".".join(str(p) for p in first["loc"] if not isinstance(p, int))
    return f"it does not fit the page change it becomes ({where + ': ' if where else ''}{first['msg']})."


def _structural_change(r: Recommendation, expected_original: str):
    """The typed change for a structural recommendation (J5, J11, J12, J14, S3), or None for an ordinary text edit.

    Raises ValidationError when the suggestion does not fit the action (for example a 58-character heading).
    """
    metric = r.type.upper()
    if metric == "J5":
        return SetLinkText(block_id=r.block_id, text=r.suggestion, expected_original=expected_original)
    if metric == "J12":
        return SetAltText(block_id=r.block_id, alt=r.suggestion, expected_original=expected_original)
    if metric == "J14":
        return SetButtonLabel(block_id=r.block_id, label=r.suggestion, expected_original=expected_original)
    if metric == "S3":
        return AddSectionHeading(block_id=r.block_id, heading=r.suggestion, expected_original=expected_original)
    if metric == "J11":
        return AddButtonLabel(block_id=r.block_id, label=r.suggestion, expected_original=expected_original or None)
    return None


def _generate_plain(
    text_recs: list[Recommendation], layout_recs: list[Recommendation], blocks: list[dict] | None
) -> AdaptedUIResult:
    """Build the spec one change at a time. A change the spec rejects is reported in `skipped`; it never takes the
    other accepted changes down with it."""
    text_ok, layout_ok, skipped = select_usable(text_recs, layout_recs, blocks)
    block_text = {
        b["block_id"]: b.get("alt", "") if b.get("kind") == "img" else b.get("text", "")
        for b in blocks or []
    }

    def skip(ids: list[str], reason: str) -> None:
        skipped.extend(SkippedRecommendation(id=i, reason=reason) for i in ids)

    new_text: dict[str, str] = {}
    new_text_ids: dict[str, list[str]] = {}
    structural: list[tuple[list[str], object]] = []
    content_blocks: set[str] = set()
    for r in text_ok:
        try:
            special = _structural_change(r, block_text[r.block_id])
        except ValidationError as e:
            skip([r.id], _why(e))
            continue
        if special is not None:
            if r.block_id in content_blocks:
                skip([r.id], f"another content or structural change already targets '{r.block_id}'.")
            else:
                structural.append(([r.id], special))
                content_blocks.add(r.block_id)
            continue
        if r.block_id in content_blocks and r.block_id not in new_text:
            skip([r.id], f"a structural change already targets '{r.block_id}'.")
            continue
        if not r.original.strip():
            skip([r.id], "there is no original text to replace.")
            continue
        current = new_text.get(r.block_id, block_text[r.block_id])
        match = _find(current, r.original)
        if match is None:  # an earlier accepted edit overlapped this one
            skip([r.id], f"another accepted edit already changed the text of '{r.original[:40]}...'.")
            continue
        new_text[r.block_id] = current[: match.start()] + r.suggestion + current[match.end() :]
        new_text_ids.setdefault(r.block_id, []).append(r.id)
        content_blocks.add(r.block_id)

    styles: dict[str, dict[str, str]] = {}
    style_ids: dict[str, list[str]] = {}
    for r, declarations in layout_ok:
        styles.setdefault(r.block_id, {}).update(declarations)  # later recommendations win per property
        style_ids.setdefault(r.block_id, []).append(r.id)

    owned: list[tuple[list[str], object]] = []  # (recommendation ids, change), so a rejected change can say whose it was
    for block_id, text in new_text.items():
        try:
            owned.append((new_text_ids[block_id], ReplaceText(block_id=block_id, value=text)))
        except ValidationError as e:
            skip(new_text_ids[block_id], _why(e))
    owned += structural
    for block_id, declarations in styles.items():
        try:
            owned.append((style_ids[block_id], SetStyle(block_id=block_id, value=format_css(declarations))))
        except ValidationError as e:
            skip(style_ids[block_id], _why(e))

    for ids, _ in owned[MAX_CHANGES:]:
        skip(ids, f"one spec can hold at most {MAX_CHANGES} changes.")
    return AdaptedUIResult(spec=AdaptedUISpec(changes=[change for _, change in owned[:MAX_CHANGES]]), skipped=skipped)


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
