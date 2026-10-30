"""Call 2: generate_layout_recommendations. Needs a vision-capable model.

Input:  a screenshot (PNG/JPEG/WebP bytes, or base64 text) + DOM metrics (font size, line height, line length).
Output: a plain list[Recommendation] in the team's shared format, all status 'pending'.

Reference targets are imported from guidelines.py (the team's single source of truth), never copied here.
"""
import base64
import binascii
import logging
import re
from functools import partial

from ..guidelines import BODY_FONT_PX, HEADING_SCALE, LEVEL1_GUIDELINES, LINE_HEIGHT, MAX_LINE_CH
from .client import call_model
from .config import ModelConfig
from .adapted_ui_spec import parse_css
from .guards import check_known_blocks, check_rationale_numbers, check_status_pending
from .prompts import attach_image, build_messages
from .runner import DEFAULT_MAX_RECOMMENDATIONS, cap_by_severity, renumber, run_recommendation_task
from .schemas import Recommendation, RecommendationList

log = logging.getLogger("app.model")
TASK = "layout_recs"
CSS_TYPES = ("font_size", "line_spacing", "line_length", "heading_size")  # their suggestion must be a CSS declaration
_RULE_IDS = ("L1.1.2", "L1.1.3", "L1.1.6", "L1.3.2")  # font size, heading size, line spacing, line length


def layout_targets() -> dict:
    """Reference targets: the values the adapter applies, plus the guideline sentences with their ranges."""
    rules = {g.id: g.rule for g in LEVEL1_GUIDELINES if g.id in _RULE_IDS}
    if set(rules) != set(_RULE_IDS):
        raise RuntimeError(f"guidelines.py no longer has all of {_RULE_IDS}; update layout_recs.py.")
    return {
        "applied_by_adapter": {
            "font_size_px": BODY_FONT_PX,
            "line_height": LINE_HEIGHT,
            "max_line_length_chars": MAX_LINE_CH,
            "smallest_heading_scale": min(HEADING_SCALE.values()),
        },
        "guideline_rules": rules,
    }


def layout_ranges() -> dict[str, float]:
    """The guideline limits as numbers, read from the imported rule sentences (so they cannot drift from guidelines.py).

    Raises RuntimeError if a sentence no longer has the expected wording: better loud than silently wrong.
    """
    rules = layout_targets()["guideline_rules"]
    found = {
        "min_font_size_px": re.search(r"\((\d+) to \d+ pixels\)", rules["L1.1.2"]),
        "min_line_height": re.search(r"at least (\d+(?:\.\d+)?)", rules["L1.1.6"]),
        "max_line_length_chars": re.search(r"\d+ to (\d+) characters", rules["L1.3.2"]),
    }
    missing = [name for name, m in found.items() if m is None]
    if missing:
        raise RuntimeError(f"Could not read {missing} from the guideline sentences in guidelines.py; update layout_ranges().")
    return {name: float(m.group(1)) for name, m in found.items()}


# CSS property -> (metric key, True if the measurement is fine when >= the limit, limit name, required unit)
_RANGE_CHECKS = {
    "font-size": ("font_size_px", True, "min_font_size_px", "px"),
    "line-height": ("line_height", True, "min_line_height", ""),
    "max-width": ("line_length_chars", False, "max_line_length_chars", "ch"),
}


def drop_in_range(recs: list[Recommendation], metrics: dict) -> list[Recommendation]:
    """Remove recommendations that "fix" a measurement already inside the guideline range (for example font-size at 16px).

    Only single-property CSS suggestions are judged, and only when the block's measurement is known; anything else is kept.
    For block_id "page" the recommendation is dropped only if every measured block is in range.
    """
    limits, by_block = layout_ranges(), {b["block_id"]: b for b in metrics["blocks"]}
    kept = []
    for r in recs:
        try:
            props = parse_css(r.suggestion)
        except ValueError:
            kept.append(r)
            continue
        if len(props) != 1 or r.type == "heading_size":
            kept.append(r)
            continue
        prop, value = next(iter(props.items()))
        check = _RANGE_CHECKS.get(prop)
        if check is None or not value.endswith(check[3]):
            kept.append(r)
            continue
        key, fine_when_at_least, limit_name, _ = check
        blocks = by_block.values() if r.block_id == "page" else [by_block.get(r.block_id, {})]
        measured = [b[key] for b in blocks if isinstance(b.get(key), (int, float))]
        limit = limits[limit_name]
        in_range = bool(measured) and all((m >= limit) if fine_when_at_least else (m <= limit) for m in measured)
        if in_range:
            log.info("guard: dropped %s (%s measured %s is already inside the guideline range, limit %s)", r.id, key, measured[0], limit)
        else:
            kept.append(r)
    return kept


INSTRUCTIONS = """\
You help make a web page layout easier to read for students with dyslexia.
You get a screenshot of the page and measurements of its text blocks (font size, line height, line length), plus reference targets.

A measurement is a PROBLEM only when it is outside the range given in "guideline_rules":
- font size: a problem only if it is below the minimum of the range (a size inside the range, for example 16px, is fine; 14px is too small)
- line height: a problem only if it is below the minimum ("at least ...")
- line length: a problem only if it is above the maximum of the range
Do not report a measurement that is inside its range, even if it differs from "applied_by_adapter". Those applied values are only what you write in 'suggestion' when there IS a problem.

Compare each block's measurements with those ranges and look at the screenshot for crowded or hard-to-scan areas. Write one recommendation per PROBLEM, not per block: if several blocks share a problem, report it once with the first affected block_id, or "page" if every block is affected.

For a measurement that misses a target, use exactly these types and write 'original' and 'suggestion' as real CSS (property names with hyphens, units included):
- type "font_size": original "font-size: 14px", suggestion "font-size: 18px"
- type "line_spacing": original "line-height: 1.2", suggestion "line-height: 1.6"
- type "line_length": original "max-width: 96ch", suggestion "max-width: 65ch"
- type "heading_size": original "font-size: 1em", suggestion "font-size: 1.2em"
Take the suggested values from "applied_by_adapter" (only for real problems) and the original values from the measurements.
Other types, with a plain-English suggestion (no CSS needed):
- type "break_into_steps" when the screenshot shows a dense block that is really a sequence of steps or items.
- type "more_spacing" when the screenshot looks cramped.

Field guide:
- id: "r1", "r2", ... (the system renumbers them).
- block_id: a block from the measurements, or "page" for something page-wide.
- rationale: one short sentence. If you mention a number, copy it from the measurements or targets exactly, for example "line spacing is 1.2; target >= 1.5".
- evidence: the rule, for example "DOM metrics / guideline L1.1.6".
- severity: "high", "medium" or "low". status: "pending".
Only report real problems. If the layout already meets the targets, return {"recommendations": []}."""


def check_css_suggestions(recs: list[Recommendation]) -> list[str]:
    """For the CSS types, `suggestion` must be a real, allowed CSS declaration (call 3 turns it into a style change)."""
    problems = []
    for r in recs:
        if r.type in CSS_TYPES:
            try:
                parse_css(r.suggestion)
            except ValueError as e:
                problems.append(f"{r.id}: for type '{r.type}' the suggestion must be CSS like 'line-height: 1.6'. {e}")
    return problems


def _validate_metrics(metrics: dict) -> None:
    blocks = metrics.get("blocks") if isinstance(metrics, dict) else None
    if not blocks or not all(isinstance(b, dict) and b.get("block_id") for b in blocks):
        raise ValueError("metrics needs a non-empty 'blocks' list, each with a 'block_id'.")


def screenshot_to_data_url(screenshot: bytes | str) -> str:
    """Turn PNG/JPEG/WebP bytes (or their base64 text) into a data: URL for the model."""
    if isinstance(screenshot, str):
        text = screenshot.split(",", 1)[-1] if screenshot.startswith("data:") else screenshot
        try:
            screenshot = base64.b64decode(text, validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("screenshot is text but not valid base64.") from None
    if screenshot[:8] == b"\x89PNG\r\n\x1a\n":
        mime = "image/png"
    elif screenshot[:3] == b"\xff\xd8\xff":
        mime = "image/jpeg"
    elif screenshot[:4] == b"RIFF" and screenshot[8:12] == b"WEBP":
        mime = "image/webp"
    else:
        raise ValueError("screenshot must be a PNG, JPEG or WebP image.")
    return f"data:{mime};base64,{base64.b64encode(screenshot).decode('ascii')}"


def generate_layout_recommendations(
    screenshot: bytes | str,
    metrics: dict,
    *,
    start_id: int = 1,
    max_recommendations: int | None = DEFAULT_MAX_RECOMMENDATIONS,
    max_retries: int | None = None,
    config: ModelConfig | None = None,
    transport=None,
    caller=call_model,
) -> list[Recommendation]:
    """Return layout recommendations, or raise ModelOutputError / ModelCallError / ModelConfigError. Never invalid data."""
    _validate_metrics(metrics)
    data_url = screenshot_to_data_url(screenshot)
    config = config or ModelConfig.from_env()
    findings = {**metrics, "targets": layout_targets()}  # what the number check is run against

    checks = [check_status_pending]
    if not config.mock:  # the mock ignores its input, so input-matching checks only apply to a real model
        block_ids = {b["block_id"] for b in metrics["blocks"]} | {"page"}
        checks += [partial(check_known_blocks, block_ids=block_ids), partial(check_rationale_numbers, findings=findings), check_css_suggestions]

    messages = attach_image(build_messages(INSTRUCTIONS, RecommendationList, findings), data_url)
    recs = run_recommendation_task(
        task=TASK, messages=messages, checks=tuple(checks),
        max_retries=max_retries, config=config, transport=transport, caller=caller,
    )
    if not config.mock:  # the mock ignores its input, so it is not judged against the measurements
        recs = drop_in_range(recs, metrics)
    return renumber(cap_by_severity(recs, max_recommendations), start_id)  # pass start_id=len(text_recs)+1 so ids stay unique across calls 1 and 2
