"""Call 3, model version. Optional: plain code (adapted_ui.py) is the recommended implementation.

The model is given the accepted recommendations and the block texts and must return the placeholder spec.
Its output is accepted only if it passes checks that make it equivalent in substance to the plain-code result:
every accepted suggestion appears word for word, replaced originals are gone, numbers survive, and styles match.
"""
from functools import partial

from .adapted_ui_spec import AdaptedUIResult, AdaptedUISpec, parse_css
from .adapted_ui import select_usable
from .client import call_model
from .config import ModelConfig
from .guards import numbers_in
from .prompts import ADAPT_RULES, build_messages
from .runner import run_task
from .schemas import Recommendation

TASK = "adapted_ui"

INSTRUCTIONS = """\
You build the adapted version of a web page from the changes a user accepted.
You get the text blocks that have accepted text recommendations, the accepted text recommendations, and the accepted layout (CSS) recommendations.
Return a JSON object {"changes": [...]}. Each change has:
- block_id: the block it applies to ("page" is allowed for set_style only)
- action: "replace_text" or "set_style"
- value: see the rules"""


def _squash(text: str) -> str:
    return " ".join(text.split())


def _check_spec(
    spec: AdaptedUISpec,
    *,
    text_recs: list[Recommendation],
    layout_recs: list[tuple[Recommendation, dict[str, str]]],
    block_text: dict[str, str],
) -> list[str]:
    problems: list[str] = []
    text_blocks = {r.block_id for r in text_recs}
    style_blocks = {r.block_id for r, _ in layout_recs}

    replaced: dict[str, str] = {}
    styled: dict[str, dict[str, str]] = {}
    for c in spec.changes:
        if c.action == "replace_text":
            if c.block_id not in text_blocks:
                problems.append(f"replace_text for '{c.block_id}', which has no accepted text recommendation.")
            elif c.block_id in replaced:
                problems.append(f"More than one replace_text for '{c.block_id}'. Merge them into one.")
            replaced[c.block_id] = c.value
        else:
            if c.block_id not in style_blocks:
                problems.append(f"set_style for '{c.block_id}', which has no accepted layout recommendation.")
            elif c.block_id in styled:
                problems.append(f"More than one set_style for '{c.block_id}'. Merge them into one.")
            styled[c.block_id] = parse_css(c.value)

    for block_id in sorted(text_blocks):
        value = replaced.get(block_id)
        if value is None:
            problems.append(f"Missing replace_text for '{block_id}'.")
            continue
        squashed = _squash(value)
        recs = [r for r in text_recs if r.block_id == block_id]
        for r in recs:
            if _squash(r.suggestion) not in squashed:
                problems.append(f"{r.id}: the accepted suggestion must appear word for word in the text of '{block_id}'.")
            elif _squash(r.original) in squashed and _squash(r.original) not in _squash(r.suggestion):
                problems.append(f"{r.id}: the original text is still in '{block_id}'; it should have been replaced.")
        allowed_numbers = numbers_in(block_text[block_id]) | numbers_in([r.suggestion for r in recs])
        extra = sorted(numbers_in(value) - allowed_numbers)
        lost = sorted(numbers_in(block_text[block_id]) - numbers_in(value) - numbers_in([r.original for r in recs]))
        if extra or lost:
            problems.append(f"Numbers changed in '{block_id}' (added: {extra or 'none'}, lost: {lost or 'none'}). Keep every number exactly.")

    for block_id in sorted(style_blocks):
        got = styled.get(block_id)
        if got is None:
            problems.append(f"Missing set_style for '{block_id}'.")
            continue
        for r, wanted in ((r, d) for r, d in layout_recs if r.block_id == block_id):
            wrong = {p: v for p, v in wanted.items() if got.get(p) != v}
            if wrong:
                problems.append(f"{r.id}: set_style for '{block_id}' must contain exactly {wrong}.")
    return problems


def generate_adapted_ui_with_model(
    text_recs: list[Recommendation],
    layout_recs: list[Recommendation],
    blocks: list[dict] | None = None,
    *,
    max_retries: int | None = None,
    config: ModelConfig | None = None,
    transport=None,
    caller=call_model,
) -> AdaptedUIResult:
    config = config or ModelConfig.from_env()
    text_ok, layout_ok, skipped = select_usable(text_recs, layout_recs, blocks)
    if not text_ok and not layout_ok:  # nothing to build: no reason to call a model
        return AdaptedUIResult(spec=AdaptedUISpec(changes=[]), skipped=skipped)

    block_text = {b["block_id"]: b["text"] for b in blocks or []}
    data = {
        "blocks": [{"block_id": b, "text": block_text[b]} for b in dict.fromkeys(r.block_id for r in text_ok)],
        "accepted_text_recommendations": [
            {"id": r.id, "block_id": r.block_id, "original": r.original, "suggestion": r.suggestion} for r in text_ok
        ],
        "accepted_layout_recommendations": [
            {"id": r.id, "block_id": r.block_id, "suggestion": r.suggestion} for r, _ in layout_ok
        ],
    }
    # The mock returns a fixed reply that ignores its input, so only the schema check applies to it.
    checks = () if config.mock else (partial(_check_spec, text_recs=text_ok, layout_recs=layout_ok, block_text=block_text),)
    spec = run_task(
        task=TASK, messages=build_messages(INSTRUCTIONS, AdaptedUISpec, data, rules=ADAPT_RULES),
        schema=AdaptedUISpec, checks=checks, max_retries=max_retries, config=config, transport=transport, caller=caller,
    )
    return AdaptedUIResult(spec=spec, skipped=skipped)
