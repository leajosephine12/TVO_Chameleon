"""The two operations the backend exposes for the general-accessibility flow.

    analyze_general(html)         measure -> model proposes -> guardrails -> recommendations (all 'pending')
    apply_general(html, recs)     the accepted recommendations' typed changes, applied by the renderer

Same shape as the dyslexia flow: /analyze returns recommendations, the UI collects decisions, /adapted applies them.
"""
from app.adaptation_engine import _index_blocks
from app.model.adapted_renderer import apply_adapted_spec, block_text
from app.model.adapted_ui import _find
from app.model.adapted_ui_spec import AdaptedUISpec, Change
from app.model.client import ModelCallError
from app.model.config import ModelConfigError
from app.model.runner import ModelOutputError
from bs4 import BeautifulSoup
from pydantic import TypeAdapter, ValidationError

from .computed import COMPUTED_METRICS, computed_recommendations
from .measure import measure
from .planner import plan_changes
from .schemas import A11yRecommendation

MODEL_ERRORS = (ModelConfigError, ModelCallError, ModelOutputError)
APPROVED = ("accepted", "edited")
_CHANGE = TypeAdapter(Change)
# The one field a reviewer's edit of `suggestion` replaces, per typed change.
_EDIT_FIELD = {
    "set_style": "value", "set_link_text": "text", "set_button_label": "label", "add_button_label": "label",
    "set_alt_text": "alt", "add_section_heading": "heading", "add_heading_before": "heading",
}


def _capped(findings: list[dict], per_metric: int = 10) -> list[dict]:
    seen: dict[str, int] = {}
    out = []
    for f in findings:
        seen[f["metric_id"]] = seen.get(f["metric_id"], 0) + 1
        if seen[f["metric_id"]] <= per_metric:
            out.append(f)
    return out


def analyze_general(html: str, url: str | None = None, rendered: dict | None = None, **plan_options) -> dict:
    findings = measure(html, url, uncapped=True)
    if rendered:
        findings += rendered["findings"]
    # Layout fixes are computed, not proposed: they ship even when the model step fails (see computed.py).
    recommendations, computed_rejected = computed_recommendations(html, findings)
    report, model_error = None, None
    try:
        for_model = [f for f in findings if f["metric_id"] not in COMPUTED_METRICS]
        plan = plan_changes(html, for_model, **{"start_id": len(recommendations) + 1, **plan_options})
        recommendations, report = recommendations + plan.recommendations, plan.report()
        report["rejected"] = computed_rejected + report["rejected"]
    except MODEL_ERRORS as e:
        model_error = str(e)  # the measured findings still ship; the UI can say the model step failed
    return {"level": "general", "recommendations": recommendations, "model_error": model_error,
            "findings": _capped(findings), "guardrails": report}


def _edited_change(rec: A11yRecommendation, html: str) -> dict:
    """The change as stored, with the reviewer's edit of `suggestion` put into the one field it stands for."""
    change = dict(rec.change)
    if rec.status != "edited":
        return change
    if change["action"] in _EDIT_FIELD:
        change[_EDIT_FIELD[change["action"]]] = rec.suggestion
    elif change["action"] == "replace_text" and rec.original:
        tag = _index_blocks(BeautifulSoup(html, "html.parser")).get(rec.block_id)
        match = _find(block_text(tag), rec.original) if tag is not None else None
        if match is not None:
            text = block_text(tag)
            change["value"] = text[: match.start()] + rec.suggestion + text[match.end():]
    return change


def apply_general(html: str, recs: list[A11yRecommendation]) -> dict:
    """Apply the accepted/edited recommendations that carry a typed change. Anything the spec or the live page
    rejects is skipped with a reason; one bad change never takes the others down."""
    changes, owners, reasons = [], [], {}
    for rec in recs:
        if rec.change is None or rec.status not in APPROVED:
            continue
        try:
            change = _CHANGE.validate_python(_edited_change(rec, html))
            AdaptedUISpec(changes=[*changes, change])  # the one-change-per-block rules
        except ValidationError as e:
            first = e.errors()[0]
            reasons[rec.id] = f"it does not fit the page change it becomes ({first['msg']})."
            continue
        changes.append(change)
        owners.append(rec.id)
    result = apply_adapted_spec(html, AdaptedUISpec(changes=changes))
    for i, reason in result.skipped.items():
        reasons[owners[i]] = reason
    applied = [owner for i, owner in enumerate(owners) if i not in result.skipped]
    return {"adapted_html": result.html, "applied": applied, "skipped": list(reasons), "skipped_reasons": reasons}
