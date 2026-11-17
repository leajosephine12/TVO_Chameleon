"""
dyslexia_engine/app/levels/level2_plain_text.py

Level 2, call 1: generate_text_recommendations. Text only, no vision.
Originally from model/text_recs.py.

Input:  text blocks + findings (from analyze_text; the findings shape is a PROPOSAL, see README).
Output: a plain list[Recommendation] in the team's shared format, all status 'pending'.

What changed from text_recs.py:
- The prompt is built from the Level 2 guidelines by build_level2_instructions()
  (model/instructions/level2_plain_text.py), so it cannot drift from
  guidelines/level2_plain_text.py.
- New optional `enabled_rules`: pass a set like {"L2.1.2", "L2.1.3"} to apply only some rules.
- The cap line now mentions every plain-language rewrite, not only difficult words.
Everything else (guards, runner, renumbering) is unchanged.

Key change: build_level2_instructions instead of INSTRUCTION text
"""
import re
from functools import partial

from ..model.client import call_model
from ..model.config import ModelConfig
from ..model.guards import (
    check_judgement_evidence,
    check_known_blocks,
    check_meaning_preserved,
    check_original_is_quoted,
    check_rationale_numbers,
    check_status_pending,
    check_structural_fields,
)
# new
from ..model.per_level_prompts.level2_plain_text import build_level2_instructions
from ..model.prompts import build_messages, judgement_section
from ..model.runner import DEFAULT_MAX_RECOMMENDATIONS, cap_by_severity, renumber, run_recommendation_task
from ..schemas import Recommendation, AnalyzeResult
from ..model.schemas import RecommendationList
from ..model.analyze_level2 import analyze_level2_plain_text
from ..model.schemas import Level2ApplyResult, SkippedRec, TextBlock
from ..model.guards import MAX_ITEMS, MAX_CHANGES, MAX_ITEM_CHARS, MAX_LABEL_CHARS
from ..guidelines.level2_plain_text import LEVEL2_GUIDELINES

TASK = "level2_text_recs"

# create: analyze_level2(blocks, enabled_rules=None) -> list[Recommendation]
# this was partially from dyslexia_engine/app/model/standin_analyze_text.py
def analyze_level2(
    blocks: list[dict],
    enabled_rules: set[str] | None = None,
    max_recommendations: int | None = None,
    *,
    config: ModelConfig | None = None,
    transport=None,
    caller=call_model,
) -> AnalyzeResult:
    """Level 2, step 1: analyse the text and return pending recommendations plus findings.

    blocks:              [{"block_id", "text"}]
    enabled_rules:       e.g. {"L2.1.2", "L2.1.3"}; None means every rewrite rule
    max_recommendations: None means DEFAULT_MAX_RECOMMENDATIONS
    Raises ValueError (bad input or unknown rule id), ModelConfigError, ModelCallError, ModelOutputError.
    """
    _validate_input(blocks)
    findings = analyze_level2_plain_text(blocks)
    recs = generate_text_recommendations(
        blocks,
        findings,
        max_recommendations=max_recommendations or DEFAULT_MAX_RECOMMENDATIONS,
        enabled_rules=enabled_rules,
        config=config,
        transport=transport,
        caller=caller,
    )
    return AnalyzeResult(level=2, recommendations=recs, findings=findings)

# vriti's
def _structural_limits_note() -> str:
    """The limits the typed page changes enforce, read from the spec so the prompt cannot drift from it."""
    return (
        f"\n\nLimits for the structural types: a J5, J11 or J14 label and an S3 heading are one line of at most "
        f"{MAX_LABEL_CHARS} characters; J12 alt text is at most {MAX_ITEM_CHARS} characters. For J5, J14 and S3, "
        "'original' is the current text, copied exactly, and is never empty."
    )

# vriti's
def _validate_input(blocks: list[dict]) -> None:
    if not blocks:
        raise ValueError("blocks is empty: there is no text to analyse.")
    for b in blocks:
        if not isinstance(b, dict) or not b.get("block_id") or not isinstance(b.get("text"), str):
            raise ValueError("Each block needs a 'block_id' and a 'text' string.")


_RULE_ID = re.compile(r"L2\.\d+\.\d+")
def _evidence_from_sources(recs: list[Recommendation]) -> list[Recommendation]:
    """Replace the model's rule ids with 'ids / source', taking each source from Guideline.source.

    The model only names the rule ids; the citation text comes from LEVEL2_GUIDELINES, so it is
    always exact. 'model judgement / <id>' evidence is left untouched.
    """
    by_id = {g.id: g for g in LEVEL2_GUIDELINES}
    out = []
    for r in recs:
        if r.evidence.strip().startswith("model judgement"):
            out.append(r)
            continue
        ids = list(dict.fromkeys(_RULE_ID.findall(r.evidence)))  # de-duplicate, keep order
        sources = list(dict.fromkeys(by_id[i].source for i in ids if i in by_id))
        if sources:
            r = r.model_copy(update={"evidence": f"{', '.join(ids)} / {'; '.join(sources)}"})
        out.append(r)
    return out


# vriti's -- internal funciton for testing
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
    enabled_rules: set[str] | None = None,
) -> list[Recommendation]:
    """Return Level 2 text recommendations (ids r{start_id}, r{start_id+1}, ...), or raise ModelOutputError / ModelCallError / ModelConfigError. Never invalid data.

    judgement_checks: optional bucket-4 metrics (id -> instruction) the model may judge itself,
    labeled evidence "model judgement / <id>". Unknown ids are rejected by the guard.
    enabled_rules: optional Level 2 rule ids (for example {"L2.1.2", "L2.1.3"}). None means every rewrite rule.
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
            check_structural_fields,
        ]
        if judgement_checks:
            checks.append(partial(check_judgement_evidence, judgement_ids=set(judgement_checks)))

    instructions = build_level2_instructions(enabled_rules) + _structural_limits_note()
    if max_recommendations:  # the cap travels with the call, so the prompt and cap_by_severity agree
        instructions += (
            f"\n- At most {max_recommendations} recommendations: every long sentence first, "
            "then the other plain-language rewrites if there is room."
        )
    if judgement_checks:
        instructions += judgement_section(judgement_checks)
    messages = build_messages(instructions, RecommendationList, {"blocks": blocks, "findings": findings})
    recs = run_recommendation_task(
        task=TASK, messages=messages, checks=tuple(checks),
        max_retries=max_retries, config=config, transport=transport, caller=caller,
    )
    recs = _evidence_from_sources(recs) # guarantees that the eveidence part is from "source"
    return renumber(cap_by_severity(recs, max_recommendations), start_id)

# create apply_level2(blocks, accepted_recs)
def apply_level2(blocks: list[dict], accepted: list[Recommendation]) -> Level2ApplyResult:
    """Swap each accepted recommendation's `original` for its `suggestion`.

    A change is applied only if its block exists and `original` appears exactly once in that
    block's current text. Anything else goes to `skipped` with a reason. Input blocks are not mutated.
    """
    text = {b["block_id"]: b["text"] for b in blocks}
    applied, skipped = [], []
    for rec in accepted:
        if rec.block_id not in text:
            skipped.append(SkippedRec(id=rec.id, reason="unknown block"))
            continue
        n = text[rec.block_id].count(rec.original) if rec.original else 0
        if n == 0:
            skipped.append(SkippedRec(id=rec.id, reason="original text not found"))
        elif n > 1:
            skipped.append(SkippedRec(id=rec.id, reason="original text ambiguous"))
        else:
            text[rec.block_id] = text[rec.block_id].replace(rec.original, rec.suggestion, 1)
            applied.append(rec.id)
    return Level2ApplyResult(
        blocks=[TextBlock(block_id=b["block_id"], text=text[b["block_id"]]) for b in blocks],
        applied=applied,
        skipped=skipped,
    )