"""Call 2: generate_layout_recommendations. Needs a vision-capable model.

Input:  a screenshot (PNG/JPEG/WebP bytes, or base64 text) + DOM metrics (font size, line height, line length).
Output: a plain list[Recommendation] in the team's shared format, all status 'pending'.

Reference targets are imported from guidelines.py (the team's single source of truth), never copied here.
"""
import base64
import binascii
from functools import partial

from ..guidelines import BODY_FONT_PX, HEADING_SCALE, LEVEL1_GUIDELINES, LINE_HEIGHT, MAX_LINE_CH
from .client import call_model
from .config import ModelConfig
from .guards import check_known_blocks, check_rationale_numbers, check_status_pending, check_unique_ids
from .prompts import attach_image, build_messages
from .runner import run_recommendation_task
from .schemas import Recommendation, RecommendationList

TASK = "layout_recs"
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


INSTRUCTIONS = """\
You help make a web page layout easier to read for students with dyslexia.
You get a screenshot of the page and measurements of its text blocks (font size, line height, line length), plus reference targets.

Compare each block's measurements with the targets and look at the screenshot for crowded or hard-to-scan areas. Write one recommendation per problem, for example:
- type "font_size", "line_spacing", "line_length" or "heading_size" when a measurement misses a target. In 'suggestion' give the fix as CSS using a value from "applied_by_adapter".
- type "break_into_steps" when the screenshot shows a dense block that is really a sequence of steps or items.
- type "more_spacing" when the screenshot looks cramped.

Field guide:
- id: "r1", "r2", ... unique.
- block_id: a block from the measurements, or "page" for something page-wide.
- original: what the page does now, for example "line-height: 1.2" (copy the measured value).
- rationale: one short sentence. If you mention a number, copy it from the measurements or targets exactly, for example "line spacing is 1.2; target >= 1.5".
- evidence: the rule, for example "DOM metrics / guideline L1.1.6".
- severity: "high", "medium" or "low". status: "pending".
Only report real problems. If the layout already meets the targets, return {"recommendations": []}."""


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

    checks = [check_unique_ids, check_status_pending]
    if not config.mock:  # the mock ignores its input, so input-matching checks only apply to a real model
        block_ids = {b["block_id"] for b in metrics["blocks"]} | {"page"}
        checks += [partial(check_known_blocks, block_ids=block_ids), partial(check_rationale_numbers, findings=findings)]

    messages = attach_image(build_messages(INSTRUCTIONS, RecommendationList, findings), data_url)
    return run_recommendation_task(
        task=TASK, messages=messages, checks=tuple(checks),
        max_retries=max_retries, config=config, transport=transport, caller=caller,
    )
