"""Layout fixes that need no model: the measurement and the threshold already say what the CSS must be.

Text size (L3), line spacing and justified text (L2) and line length (L1) are measured on the rendered page.
The fix is the threshold itself, so code writes it. It goes through the same guardrails, preview and apply path as a
model proposal, and it is still there when the model is slow, wrong or switched off.
(L4 target size and L12 font count stay with the model: which padding or which font is a choice, not a number.)
"""
from accessibility_metrics.thresholds import THRESHOLDS

from .context import build_context
from .guardrails import check_proposal
from .policy import MAX_CHANGES
from .recommend import to_recommendation
from .schemas import A11yRecommendation, Proposal

COMPUTED_METRICS = ("L1", "L2", "L3")
_WHY = {"L1": "Lines are longer than the limit.", "L2": "Lines are too close together or justified.",
        "L3": "Text is smaller than the limit."}


def _css(f: dict) -> str:
    measured, t = f["measured"], THRESHOLDS[f["metric_id"]]
    if f["metric_id"] == "L1":
        return f"max-width: {t['max_chars']}ch"
    if f["metric_id"] == "L3":
        return f"font-size: {t['min_px']:g}px"
    parts = []
    if measured.get("line_height", t["min_line_height"]) < t["min_line_height"]:
        parts.append(f"line-height: {t['min_line_height']}")
    if measured.get("text_align") == "justify":
        parts.append("text-align: left")
    return "; ".join(parts)


def computed_recommendations(html: str, findings: list[dict], start_id: int = 1) -> tuple[list[A11yRecommendation], list[dict]]:
    """(recommendations, rejected) for the layout findings among `findings`. Never calls a model.

    One recommendation per block: a paragraph that is both small and cramped gets one card with both declarations,
    because the page-change spec allows one style change per block."""
    ctx = build_context(html, [f for f in findings if f["metric_id"] in COMPUTED_METRICS], judgement=False)
    ctx.baseline = findings
    per_block: dict[str, list[Proposal]] = {}
    rejected = []
    for f in ctx.findings:
        p = Proposal.model_validate({
            "metric_id": f["metric_id"], "block_id": f["block_id"], "rationale": _WHY[f["metric_id"]],
            "change": {"action": "set_style", "block_id": f["block_id"], "value": _css(f)},
        })
        _, problems = check_proposal(p, ctx)
        if problems:
            rejected.append({"metric_id": p.metric_id, "block_id": p.block_id, "action": "set_style", "reasons": problems})
        else:
            per_block.setdefault(p.block_id, []).append(p)

    recs = []
    for block_id, proposals in list(per_block.items())[:MAX_CHANGES]:  # reviewer attention is the budget
        parts = [to_recommendation(0, p, p.change, ctx, None, p.change.value) for p in proposals]
        css = "; ".join(r.preview_css for r in parts)
        recs.append(parts[0].model_copy(update={
            "id": f"r{start_id + len(recs)}",
            "type": "+".join(r.type for r in parts),
            "title": parts[0].title if len(parts) == 1 else "Text is hard to read as laid out",
            "original": "; ".join(r.original for r in parts), "suggestion": css,
            "rationale": " ".join(r.rationale for r in parts), "evidence": " ".join(r.evidence for r in parts),
            "change": {"action": "set_style", "block_id": block_id, "value": css}, "preview_css": css,
        }))
    return recs, rejected
