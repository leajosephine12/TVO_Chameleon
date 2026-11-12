"""Turn the page and its findings into what the model is shown: only problems it is allowed to act on, with the
block text it needs to quote exactly. Everything here is selection and quoting; no wording is decided in code."""
import re
from dataclasses import dataclass, field

from accessibility_metrics.judgement import TEXT_JUDGEMENT
from accessibility_metrics.thresholds import THRESHOLDS
from app.adaptation_engine import _index_blocks
from app.model.adapted_renderer import block_text
from bs4 import BeautifulSoup, Tag

from .measure import PROSE_TAGS
from .policy import (
    JUDGEMENT_METRICS, MAX_ANCHORS, MAX_BLOCK_CHARS, MAX_FINDINGS_IN_PROMPT, MAX_JUDGEMENT_BLOCKS, POLICY, TIER_ORDER,
)

_BLOCK_ID = re.compile(r"^[a-z][a-z0-9]*-\d+$")
_ANCHOR_TAGS = {"p", "ul", "ol", "section", "article", "table", "figure", "blockquote", "div"}


@dataclass
class Context:
    html: str
    soup: BeautifulSoup
    index: dict[str, Tag]
    findings: list[dict]  # actionable findings, in prompt order
    blocks: dict[str, dict]  # block_id -> what the model sees about it
    anchors: list[str] = field(default_factory=list)  # blocks a page-wide finding may point at
    judgement_blocks: list[str] = field(default_factory=list)
    terms: dict[str, list[str]] = field(default_factory=dict)  # unexplained abbreviation -> blocks that contain it
    judgement: dict[str, str] = field(default_factory=dict)
    baseline: list[dict] = field(default_factory=list)  # every finding on the unchanged page, uncapped (for the re-measure gate)
    applied_html: str | None = None  # the page after the proposal being checked (set by the applies_cleanly check)

    def text(self, block_id: str) -> str:
        return block_text(self.index[block_id])

    def findings_for(self, metric_id: str) -> list[dict]:
        return [f for f in self.findings if f["metric_id"] == metric_id]


def is_actionable(f: dict, index: dict[str, Tag]) -> bool:
    """A finding the model may be asked to fix: the metric has a policy, and the finding points at something real."""
    policy = POLICY.get(f["metric_id"])
    if policy is None or policy.scope == "judgement" or f.get("report_only"):
        return False
    block_id, m = f["block_id"], f.get("measured", {})
    if f["metric_id"] == "T8":
        return bool(m.get("abbreviation"))
    if policy.scope == "anchor":
        return True
    if f["metric_id"] == "S5" and "items" not in m:  # a list item with several sentences has no safe typed change
        return False
    if f["metric_id"] == "N8" and "links" not in m:  # menu depth has no safe typed change
        return False
    if f["metric_id"] == "L12":
        return block_id == "page"
    return bool(_BLOCK_ID.match(block_id)) and block_id in index


def _describe(block_id: str, tag: Tag, ids: dict[int, str]) -> dict:
    """What the model needs to know about a block to change it. `ids` maps id(tag) -> block id for the whole page."""
    info: dict = {"block_id": block_id, "kind": tag.name, "text": block_text(tag)[:MAX_BLOCK_CHARS]}
    if tag.name == "a":
        info["href"] = tag.get("href", "")
    if tag.name == "img":
        src = (tag.get("src") or "").rsplit("/", 1)[-1]
        info.update(file_name=src, alt=tag.get("alt", ""))
    if tag.name in {"a", "button"} or tag.get("role") == "button":
        hints = [tag.get("aria-label"), tag.get("title"), " ".join(tag.get("class", []))]
        info["hint"] = " ".join(h for h in hints if h)[:120]
    if tag.name in {"ul", "ol"}:
        info["items"] = [
            {"block_id": ids[id(li)], "text": block_text(li)[:200]} for li in tag.find_all("li", recursive=False)
        ][:30]
    if tag.name in {"section", "article"}:
        info["has_heading"] = tag.find(["h1", "h2", "h3", "h4", "h5", "h6"]) is not None
        info["text"] = info["text"][:600]
    if tag.name in {"video", "audio"}:
        info["autoplay"] = tag.has_attr("autoplay")
    return info


def build_context(html: str, findings: list[dict], *, judgement: bool = True) -> Context:
    soup = BeautifulSoup(html, "html.parser")
    index = _index_blocks(soup)
    ids = {id(tag): block_id for block_id, tag in index.items()}

    def describe(block_id: str) -> dict:
        return _describe(block_id, index[block_id], ids)

    actionable = [f for f in findings if is_actionable(f, index)]
    actionable.sort(key=lambda f: (TIER_ORDER.get(f.get("tier", "F"), 9), list(POLICY).index(f["metric_id"])))
    # Take turns between metrics before cutting: a page with twenty hard paragraphs must not hide every other problem.
    turns, seen = [], {}
    for f in actionable:
        seen[f["metric_id"]] = seen.get(f["metric_id"], 0) + 1
        turns.append(seen[f["metric_id"]])
    by_turn = sorted(zip(turns, range(len(actionable))))  # the index keeps the tier order inside each turn
    actionable = [actionable[i] for _, i in by_turn[:MAX_FINDINGS_IN_PROMPT]]

    ctx = Context(html=html, soup=soup, index=index, findings=actionable, blocks={})
    for f in actionable:
        if f["block_id"] in index and f["block_id"] not in ctx.blocks:
            ctx.blocks[f["block_id"]] = describe(f["block_id"])

    if any(POLICY[f["metric_id"]].scope == "anchor" for f in actionable):
        for block_id, tag in index.items():
            if tag.name in _ANCHOR_TAGS and block_text(tag).strip() and len(ctx.anchors) < MAX_ANCHORS:
                previous = tag.find_previous_sibling()
                if previous is not None and previous.name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
                    continue  # already has a heading in front of it
                if tag.name in {"p", "ul", "ol", "table", "figure", "blockquote"} or (
                    tag.name in {"section", "article", "div"} and not tag.find(_ANCHOR_TAGS)
                ):
                    ctx.anchors.append(block_id)
                    ctx.blocks.setdefault(block_id, {**describe(block_id), "text": block_text(tag)[:200]})

    for f in actionable:
        if f["metric_id"] == "T8":
            term = f["measured"]["abbreviation"]
            holders = [b for b, tag in index.items() if tag.name in PROSE_TAGS and re.search(rf"(?<!\w){re.escape(term)}(?!\w)", block_text(tag))]
            if holders:
                ctx.terms[term] = holders[:5]
                for b in holders[:5]:
                    ctx.blocks.setdefault(b, describe(b))

    if judgement:
        ctx.judgement = {m: TEXT_JUDGEMENT[m] for m in JUDGEMENT_METRICS if m in TEXT_JUDGEMENT}
        for block_id, tag in index.items():
            if tag.name in {"p", "li", "blockquote"} and len(block_text(tag).split()) >= 8:
                ctx.judgement_blocks.append(block_id)
                ctx.blocks.setdefault(block_id, describe(block_id))
                if len(ctx.judgement_blocks) >= MAX_JUDGEMENT_BLOCKS:
                    break
    return ctx


def findings_view(ctx: Context) -> list[dict]:
    """The findings as the model reads them: where, what was measured, the limit, and the source."""
    return [
        {
            "metric_id": f["metric_id"], "block_id": f["block_id"], "measured": f["measured"],
            "detail": f["detail"], "limit": f["threshold"], "source": f["source"],
        }
        for f in ctx.findings
    ]


def threshold_source(metric_id: str) -> tuple[str, str]:
    t = THRESHOLDS.get(metric_id, {})
    return t.get("threshold", ""), t.get("source", "")
