"""Turn an accepted proposal into the Recommendation the review UI shows.

The evidence line is built here from the finding that triggered the change (metric, what was measured, the limit,
the source), never written by the model, so it cannot cite something that was not measured."""
from .context import Context, threshold_source
from .policy import POLICY
from .schemas import A11yRecommendation, Proposal, RewriteText


def _finding_for(p: Proposal, ctx: Context) -> dict | None:
    found = ctx.findings_for(p.metric_id)
    term = getattr(p.change, "term", None)
    return next((f for f in found if (term and f["measured"].get("abbreviation") == term) or f["block_id"] == p.block_id), None)


def evidence(p: Proposal, ctx: Context) -> str:
    f = _finding_for(p, ctx)
    if f is not None:
        return f"{p.metric_id}: {f['detail']} Limit: {f['threshold']}. Source: {f['source']}."
    limit, source = threshold_source(p.metric_id)
    return f"model judgement / {p.metric_id}: {limit}. Source: {source}."


def _css_before(f: dict | None) -> str:
    m = (f or {}).get("measured", {})
    parts = []
    if "font_size_px" in m:
        parts.append(f"font-size: {m['font_size_px']:g}px")
    if "line_height" in m:
        parts.append(f"line-height: {m['line_height']:g}")
    if m.get("text_align") == "justify":
        parts.append("text-align: justify")
    if "line_length_chars" in m:
        parts.append(f"about {m['line_length_chars']} characters per line")
    if "font_families" in m:
        parts.append("fonts: " + ", ".join(m["font_families"]))
    return "; ".join(parts) or "(current style)"


def before_after(p: Proposal, change, ctx: Context) -> tuple[str, str]:
    """(what is there now, what the change makes it), as plain text for the card."""
    text = ctx.text(p.block_id) if p.block_id in ctx.index else ""
    a = change.action
    if isinstance(p.change, RewriteText):
        return p.change.original, p.change.value
    if a == "set_style":
        return _css_before(_finding_for(p, ctx)), change.value
    if a == "text_to_list":
        mark = (lambda i: "- ") if change.list_type == "bulleted" else (lambda i: f"{i + 1}. ")
        return text, "\n".join(f"{mark(i)}{item}" for i, item in enumerate(change.items))
    if a == "split_into_steps":
        steps = [f"{i + 1}. {s}" for i, s in enumerate(change.steps)]
        return text, "\n".join(([change.intro] if change.intro else []) + steps)
    if a == "split_paragraph":
        return text, "\n\n".join(change.parts)
    if a == "add_button_label":
        return "(no text, only an icon)", change.label
    if a == "set_link_text":
        return change.expected_original, change.text
    if a == "set_button_label":
        return change.expected_original, change.label
    if a == "set_alt_text":
        return change.expected_original or "(no alt text)", change.alt
    if a in {"add_section_heading", "add_heading_before"}:
        return "(no heading here)", change.heading
    if a == "split_list":
        items = ctx.blocks.get(p.block_id, {}).get("items", [])
        return "; ".join(i["text"] for i in items), "\n".join(f"{g.label} ({len(g.item_ids)} items)" for g in change.groups)
    if a == "explain_term":
        return change.term, f"{change.term}: {change.explanation}"
    if a == "stop_autoplay":
        return "Plays by itself", "Does not start by itself; controls are shown"
    return text, ""


def to_recommendation(number: int, p: Proposal, change, ctx: Context, html: str | None, css: str | None) -> A11yRecommendation:
    original, suggestion = before_after(p, change, ctx)
    policy = POLICY[p.metric_id]
    return A11yRecommendation(
        id=f"r{number}", block_id=p.block_id, type=p.metric_id, original=original, suggestion=suggestion,
        rationale=p.rationale, evidence=evidence(p, ctx), severity=p.severity, status="pending",
        title=policy.title, category=policy.category, change=change.model_dump(mode="json"),
        preview_html=html, preview_css=css,
    )
