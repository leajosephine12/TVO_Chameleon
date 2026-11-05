"""Call 1: generate_text_recommendations. Text only, no vision.

Input:  text blocks + findings (from analyze_text; the findings shape is a PROPOSAL, see README).
Output: a plain list[Recommendation] in the team's shared format, all status 'pending'.
"""
from functools import partial

from .client import call_model
from .config import ModelConfig
from .guards import (
    check_judgement_evidence,
    check_known_blocks,
    check_meaning_preserved,
    check_original_is_quoted,
    check_rationale_numbers,
    check_status_pending,
)
from .prompts import build_messages, judgement_section
from .runner import DEFAULT_MAX_RECOMMENDATIONS, cap_by_severity, renumber, run_recommendation_task
from .schemas import Recommendation, RecommendationList

TASK = "text_recs"

INSTRUCTIONS = """\
You help make web page text easier to read for students with reading difficulties (target: Grade 3-5).
You are given text blocks and findings from a readability tool: long sentences, reading levels and difficult words.

For each supported problem listed in the findings, write one recommendation. For readability findings, rewrite ONLY the affected sentence or phrase in simpler words. The supported structural findings are:
- J5: replace generic link text with a descriptive label; use type "J5".
- J11: add a short visible label to an icon-only button; use type "J11".
- J12: replace generic or filename alt text with concise useful alt text; use type "J12".
- J14: replace a vague button label with a verb plus object; use type "J14".
- S3: add a concise heading describing the section; use type "S3".
Ignore other structural findings because this call has no safe action for them.

Field guide:
- id: "r1", "r2", ... (the system renumbers them).
- block_id: the block the text came from.
- type: "long_sentence", "difficult_word", "reading_level", or a supported structural metric id above.
- original: the affected text, copied exactly from the block (it may be empty for an icon-only control).
- suggestion: for readability findings, your simpler version with the same facts, numbers and names. For J5/J11/J12/J14/S3, the new label, alt text or heading described above.
- rationale: one short sentence saying why. If you mention a number (word count, reading level, target), copy it from the findings exactly, for example "24 words; Grade 3-5 target <= 15-20".
- evidence: where the rule comes from, for example "readability tool / W3C COGA".
- severity: "high" for a problem far beyond the target, "medium" for a clear problem, "low" for a small one.
- status: "pending".
Only write recommendations for problems that appear in the findings. If there are no problems, return {"recommendations": []}.

Keep the reply short, because a long reply is slow:
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
    max_recommendations: int | None = DEFAULT_MAX_RECOMMENDATIONS,
    max_retries: int | None = None,
    config: ModelConfig | None = None,
    transport=None,
    caller=call_model,
    judgement_checks: dict[str, str] | None = None,
) -> list[Recommendation]:
    """Return text recommendations (ids r{start_id}, r{start_id+1}, ...), or raise ModelOutputError / ModelCallError / ModelConfigError. Never invalid data.

    judgement_checks: optional bucket-4 metrics (id -> instruction) the model may judge itself,
    labeled evidence "model judgement / <id>". Unknown ids are rejected by the guard.
    """
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
        if judgement_checks:
            checks.append(partial(check_judgement_evidence, judgement_ids=set(judgement_checks)))

    instructions = INSTRUCTIONS
    if max_recommendations:  # the cap travels with the call, so the prompt and cap_by_severity agree
        instructions += f"\n- At most {max_recommendations} recommendations: every long sentence first, then the hardest words if there is room."
    if judgement_checks:
        instructions += judgement_section(judgement_checks)
    messages = build_messages(instructions, RecommendationList, {"blocks": blocks, "findings": findings})
    recs = run_recommendation_task(
        task=TASK, messages=messages, checks=tuple(checks),
        max_retries=max_retries, config=config, transport=transport, caller=caller,
    )
    return renumber(cap_by_severity(recs, max_recommendations), start_id)
