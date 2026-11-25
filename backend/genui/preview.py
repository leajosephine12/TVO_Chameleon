"""What one change looks like on the page, produced by the same renderer that builds the final page.

The review UI previews a card by swapping the block for this HTML, so what a reviewer approves is exactly what the
renderer will produce later, and the browser never needs its own copy of each action.
"""
from app.adaptation_engine import _index_blocks
from app.model.adapted_renderer import apply_adapted_spec
from app.model.adapted_ui_spec import AdaptedUISpec
from bs4 import BeautifulSoup, Comment

_START, _END = "genui-start", "genui-end"


def preview(html: str, change) -> tuple[str | None, str | None]:
    """Returns (preview_html, preview_css). A style change is CSS for the block; any other change is the HTML that
    replaces the block (which may be several elements). (None, None) means it could not be rendered."""
    if change.action == "set_style":
        return None, change.value
    soup = BeautifulSoup(html, "html.parser")
    tag = _index_blocks(soup).get(change.block_id)
    if tag is None:
        return None, None
    tag.insert_before(Comment(_START))  # comments are not elements, so block ids do not move
    tag.insert_after(Comment(_END))
    result = apply_adapted_spec(str(soup), AdaptedUISpec(changes=[change]))
    if result.skipped:
        return None, None
    start, end = result.html.find(f"<!--{_START}-->"), result.html.find(f"<!--{_END}-->")
    if start < 0 or end < start:
        return None, None
    return result.html[start + len(_START) + 7 : end], None
