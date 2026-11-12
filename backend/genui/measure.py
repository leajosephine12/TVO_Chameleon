"""Measure a page with the accessibility engine. The same code runs before the model (to find problems)
and after a proposed change (to prove the problem is gone)."""
from accessibility_metrics import analyze_text, structure_checks
from app.adaptation_engine import _index_blocks
from app.model.adapted_renderer import visible_text
from bs4 import BeautifulSoup

PROSE_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote"}
UNCAPPED = 100_000  # the reviewer-facing cap of 10 per metric would hide whether one fix really removed a finding


def text_blocks(index: dict) -> list[dict]:
    """Same block ids as everywhere else (<tag>-<n>), prose with text only."""
    return [
        {"block_id": bid, "text": visible_text(tag), "kind": tag.name}
        for bid, tag in index.items()
        if tag.name in PROSE_TAGS and visible_text(tag)
    ]


def measure(html: str, url: str | None = None, *, uncapped: bool = False) -> list[dict]:
    """All text and structure findings for a page (rendered-page layout findings are added by the caller)."""
    index = _index_blocks(BeautifulSoup(html, "html.parser"))
    cap = {"max_per_metric": UNCAPPED} if uncapped else {}
    return analyze_text(text_blocks(index))["findings"] + structure_checks(html, url=url, **cap)["findings"]
