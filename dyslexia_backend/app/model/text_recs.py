"""Call 1: generate_text_recommendations. Text only, no vision.

Input:  text blocks + findings (from analyze_text; the findings shape is a PROPOSAL, see README).
Output: a plain list[Recommendation] in the team's shared format, all status 'pending'.
"""
from functools import partial

from .client import call_model
from .config import ModelConfig
from .guards import (
    check_known_blocks,
    check_meaning_preserved,
    check_original_is_quoted,
    check_rationale_numbers,
    check_status_pending,
)
from .prompts import build_messages
from .runner import renumber, run_recommendation_task
from .schemas import Recommendation, RecommendationList

TASK = "text_recs"

INSTRUCTIONS = """\
You help make web page text easier to read for students with reading difficulties (target: Grade 3-5).
You are given text blocks and findings from a readability tool: long sentences, reading levels and difficult words.

For each problem listed in the findings, write one recommendation that rewrites ONLY the affected sentence or phrase in simpler words, usually by splitting a long sentence into shorter ones or swapping a hard word for an easier one.

Field guide:
- id: "r1", "r2", ... (the system renumbers them).
- block_id: the block the text came from.
- type: "long_sentence", "difficult_word" or "reading_level".
- original: the affected text, copied exactly from the block.
- suggestion: your simpler version. Same facts, same numbers, same names.
- rationale: one short sentence saying why. If you mention a number (word count, reading level, target), copy it from the findings exactly, for example "24 words; Grade 3-5 target <= 15-20".
- evidence: where the rule comes from, for example "readability tool / W3C COGA".
- severity: "high" for a problem far beyond the target, "medium" for a clear problem, "low" for a small one.
- status: "pending".
Only write recommendations for problems that appear in the findings. If there are no problems, return {"recommendations": []}.

Keep the reply short, because a long reply is slow:
- At most 4 recommendations: every long sentence first, then the hardest words if there is room.
- 'rationale' is at most 15 words.
- Write compact JSON: no indentation and no blank lines."""


def _validate_input(blocks: list[dict]) -> None:
    if not blocks:
        raise ValueError("blocks is empty: there is no text to analyse.")
    for b in blocks:
        if not isinstance(b, dict) or not b.get("block_id") or not isinstance(b.get("text"), str):
            raise ValueError("Each block needs a 'block_id' and a 'text' string.")


def generate_text_recommendations(
    blocks: list[dict],
    findings: dict,
    *,
    start_id: int = 1,
    max_retries: int | None = None,
    config: ModelConfig | None = None,
    transport=None,
    caller=call_model,
) -> list[Recommendation]:
    """Return text recommendations (ids r{start_id}, r{start_id+1}, ...), or raise ModelOutputError / ModelCallError / ModelConfigError. Never invalid data."""
    _validate_input(blocks)
    config = config or ModelConfig.from_env()
    block_text = {b["block_id"]: b["text"] for b in blocks}

    checks = [check_status_pending]
    if not config.mock:
        # The mock returns a fixed reply that ignores the input, so checks that compare against the
        # input only make sense for a real model.
        checks += [
            partial(check_known_blocks, block_ids=set(block_text)),
            partial(check_original_is_quoted, block_text=block_text),
            partial(check_rationale_numbers, findings=findings),
            check_meaning_preserved,
        ]

    messages = build_messages(INSTRUCTIONS, RecommendationList, {"blocks": blocks, "findings": findings})
    recs = run_recommendation_task(
        task=TASK, messages=messages, checks=tuple(checks),
        max_retries=max_retries, config=config, transport=transport, caller=caller,
    )
    return renumber(recs, start_id)
