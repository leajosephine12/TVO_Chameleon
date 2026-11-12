"""The model call that decides how the page changes.

    findings (measured by code)  ->  model proposes typed changes  ->  guardrails check each one
        -> budget and overlap  ->  renderer builds the preview  ->  recommendations for the reviewer

Nothing in this file decides what a rewrite, label or heading says: that is the model's job. Code measures, checks
and applies. A proposal that fails a guardrail is dropped and reported, never shown. If every proposal fails, the
model is told why and asked again (up to MODEL_MAX_RETRIES times).
"""
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field

from app.model.client import call_model
from app.model.config import ModelConfig
from app.model.guards import extract_json
from app.model.runner import ModelOutputError
from pydantic import ValidationError

from .context import Context, build_context
from .crawl import CrawlSnapshot
from .guardrails import check_proposal, select
from .policy import MAX_CHANGES
from .preview import preview
from .prompt import build_messages
from .recommend import to_recommendation
from .schemas import A11yRecommendation, Proposal
from .standin import standin_caller

log = logging.getLogger("app.model")
TASK = "genui"
MAX_PROPOSALS_CHECKED = 40  # each one is applied and the page measured again; a runaway reply must not stall the server

# Typed changes that carry the block's current text as a precondition. The code sets it from the live block
# (the model never retypes it), so a change can never be applied to text that has since changed.
NEEDS_EXPECTED = {
    "text_to_list", "split_into_steps", "split_paragraph", "set_link_text", "set_button_label", "set_alt_text",
    "add_section_heading", "add_heading_before", "explain_term",
}


@dataclass
class PlanResult:
    recommendations: list[A11yRecommendation] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)  # {"metric_id", "block_id", "action", "reasons"}: dropped by a guardrail
    attempts: int = 0

    def report(self) -> dict:
        return {"proposed": len(self.recommendations) + len(self.rejected), "kept": len(self.recommendations),
                "rejected": self.rejected, "model_attempts": self.attempts}


def _first(e: ValidationError) -> str:
    err = e.errors()[0]
    return f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}"


def _entry(item, reasons: list[str]) -> dict:
    change = item.get("change") if isinstance(item, dict) else None
    return {
        "metric_id": item.get("metric_id") if isinstance(item, dict) else None,
        "block_id": item.get("block_id") if isinstance(item, dict) else None,
        "action": change.get("action") if isinstance(change, dict) else None,
        "reasons": reasons,
    }


_METRIC = re.compile(r"[A-Za-z]{1,2}\d{1,2}")
_BLOCK = re.compile(r"[a-z][a-z0-9]*-\d+|page")


def _tidy_ids(item: dict) -> dict:
    """Small models sometimes write "T3 Sentence is long" for "T3", or " P-2." for "p-2". Take the id out of it."""
    metric, block = item.get("metric_id"), item.get("block_id")
    if isinstance(metric, str) and (m := _METRIC.match(metric.strip())):
        item = {**item, "metric_id": m.group().upper()}
    if isinstance(block, str) and (b := _BLOCK.search(block.strip().lower())):
        item = {**item, "block_id": b.group()}
    return item


def parse_proposals(reply: str, ctx: Context) -> tuple[list[Proposal], list[dict]]:
    """Read the model's reply one proposal at a time, so one malformed proposal does not cost the others.
    Raises json.JSONDecodeError or ValueError when the reply as a whole is unusable."""
    raw = extract_json(reply)
    items = raw.get("proposals") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        raise ValueError("The reply has no 'proposals' list.")
    ok, bad = [], []
    for item in items[:MAX_PROPOSALS_CHECKED]:
        try:
            if isinstance(item, dict):
                item = _tidy_ids(item)
            change = item.get("change") if isinstance(item, dict) else None
            if isinstance(change, dict):
                # The target lives on the proposal; the typed change carries a copy of it (except replace_text).
                if change.get("action") == "replace_text":
                    change.pop("block_id", None)
                else:
                    change["block_id"] = item.get("block_id")
                if change.get("action") in NEEDS_EXPECTED and item.get("block_id") in ctx.index:
                    change["expected_original"] = ctx.text(item["block_id"])
            ok.append(Proposal.model_validate(item))
        except ValidationError as e:
            bad.append(_entry(item, [f"does not fit the typed change: {_first(e)}"]))
    return ok, bad


def _feedback(rejected: list[dict]) -> str:
    lines = [f"- {r['metric_id']} in {r['block_id']} ({r['action']}): {'; '.join(r['reasons'])}" for r in rejected[:10]]
    return "None of your proposals could be used:\n" + "\n".join(lines) + "\nReply again with ONLY the corrected JSON object."


def plan_changes(
    html: str,
    findings: list[dict],
    *,
    start_id: int = 1,
    max_changes: int | None = None,
    max_retries: int | None = None,
    config: ModelConfig | None = None,
    transport=None,
    caller=None,
    judgement: bool | None = None,
    crawl_snapshot: CrawlSnapshot | None = None,
) -> PlanResult:
    """findings: every finding on the unchanged page (uncapped); they are also the baseline for the re-measure gate.
    Raises ModelOutputError / ModelCallError / ModelConfigError like the other model calls. Never returns an invalid change."""
    config = config or ModelConfig.from_env()
    if judgement is None:
        judgement = os.environ.get("A11Y_JUDGEMENT", "1") != "0"
    max_changes = max_changes or MAX_CHANGES
    retries = config.max_retries if max_retries is None else max_retries
    ctx = build_context(html, findings, judgement=judgement, crawl_snapshot=crawl_snapshot)
    ctx.baseline = findings
    result = PlanResult()
    if not ctx.findings and not ctx.judgement_blocks:
        return result  # nothing to fix and nothing to judge: no reason to call a model
    caller = caller or (standin_caller if config.mock else call_model)

    messages = build_messages(ctx, max_changes)
    started = time.perf_counter()
    accepted: list[tuple[Proposal, object]] = []
    last_problem = ""
    for attempt in range(1, retries + 2):
        result.attempts = attempt
        t0 = time.perf_counter()
        reply = caller(messages, task=TASK, config=config, transport=transport)
        call_secs = time.perf_counter() - t0
        try:
            proposals, rejected = parse_proposals(reply, ctx)
            proposed = len(proposals) + len(rejected)
        except (json.JSONDecodeError, ValueError) as e:
            last_problem = f"The reply was not usable ({e})."
            log.info("task=%s attempt=%d/%d model_call=%.2fs outcome=unparseable", TASK, attempt, retries + 1, call_secs)
            log.info("    the reply began: %s", " ".join(reply.split())[:300])
            messages += [{"role": "assistant", "content": reply},
                         {"role": "user", "content": f"{last_problem} Reply again with ONLY the JSON object {{\"proposals\": [...]}}."}]
            continue
        accepted = []
        for p in proposals:
            change, problems = check_proposal(p, ctx)
            if problems:
                rejected.append(_entry({"metric_id": p.metric_id, "block_id": p.block_id, "change": {"action": p.change.action}}, problems))
            else:
                accepted.append((p, change))
        result.rejected += rejected
        log.info("task=%s attempt=%d/%d model_call=%.2fs proposals=%d kept=%d rejected=%d",
                 TASK, attempt, retries + 1, call_secs, proposed, len(accepted), len(rejected))
        for r in rejected[:5]:
            log.info("    rejected %s %s: %s", r["metric_id"], r["block_id"], "; ".join(r["reasons"])[:300])
        if accepted or not rejected:
            break
        messages += [{"role": "assistant", "content": reply}, {"role": "user", "content": _feedback(rejected)}]
    else:
        if not accepted and not result.rejected:
            raise ModelOutputError(TASK, retries + 1, [last_problem or "no usable reply"])

    kept, dropped = select(accepted, ctx, max_changes)
    for p, reason in dropped:
        result.rejected.append(_entry({"metric_id": p.metric_id, "block_id": p.block_id, "change": {"action": p.change.action}}, [reason]))
    number = start_id
    for p, change in kept:
        html_preview, css_preview = preview(html, change)
        if html_preview is None and css_preview is None:
            result.rejected.append(_entry({"metric_id": p.metric_id, "block_id": p.block_id, "change": {"action": p.change.action}},
                                          ["the renderer could not preview it."]))
            continue
        result.recommendations.append(to_recommendation(number, p, change, ctx, html_preview, css_preview))
        number += 1
    log.info("task=%s done total=%.2fs kept=%d rejected=%d", TASK, time.perf_counter() - started, len(result.recommendations), len(result.rejected))
    return result
