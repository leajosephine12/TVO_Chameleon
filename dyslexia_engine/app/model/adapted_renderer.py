
"""Apply a validated AdaptedUISpec to HTML without executing arbitrary HTML or DOM operations."""
import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, NavigableString, Tag

from ..adaptation_engine import _index_blocks
from .adapted_ui_spec import AdaptedUISpec

_RICH_INLINE = {"a", "b", "strong", "i", "em", "u", "code", "mark", "abbr", "span", "svg"}


@dataclass
class RenderResult:
    html: str
    applied_indices: list[int] = field(default_factory=list)
    skipped: dict[int, str] = field(default_factory=dict)


def _squash(text: str) -> str:
    return " ".join(text.split())


_BLOCK_TAGS = {
    "address", "article", "aside", "blockquote", "dd", "details", "div", "dl", "dt", "fieldset", "figcaption",
    "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li", "main", "nav", "ol",
    "p", "pre", "section", "summary", "table", "tbody", "td", "tfoot", "th", "thead", "tr", "ul",
}


def visible_text(tag: Tag) -> str:
    """The text a reader sees in `tag`, with whitespace squashed.

    A space goes between block elements and at a <br>, never between inline ones, so
    '<a>the guide</a>, then' stays 'the guide, then' (get_text(" ") would give 'the guide , then').
    Scripts, styles and comments are left out.
    """
    parts: list[str] = []
    last_block = None
    for node in tag.descendants:
        if isinstance(node, Tag):
            if node.name == "br":
                parts.append(" ")
            continue
        if type(node) is not NavigableString:  # comments, scripts, styles, doctype
            continue
        block = next((p for p in node.parents if p is tag or p.name in _BLOCK_TAGS), tag)
        if last_block is not None and block is not last_block:
            parts.append(" ")
        parts.append(str(node))
        last_block = block
    return " ".join("".join(parts).split())


def block_text(tag: Tag) -> str:
    """The text that identifies a block to the model and to expected_original: an image's alt, a button input's
    value, otherwise what a reader sees."""
    if tag.name == "img":
        return tag.get("alt", "") or ""
    if tag.name == "input":
        return tag.get("value", "") or ""
    return visible_text(tag)


def _splits_word(text: str, i: int) -> bool:
    """True when cutting `text` at index i would land in the middle of a word."""
    return 0 < i < len(text) and text[i - 1].isalnum() and text[i].isalnum()


def _replace_text(tag: Tag, value: str) -> None:
    """Make the block's text `value`. Links, bold and other inline markup survive: only the words that changed are
    edited, inside the one text node that holds them. Raises ValueError (nothing changed) when that is not possible."""
    if not _has_rich_inline(tag):
        tag.clear()
        tag.append(value)
        return
    old, new = visible_text(tag), _squash(value)
    if old == new:
        return
    n = min(len(old), len(new))
    start = 0
    while start < n and old[start] == new[start]:
        start += 1
    end = 0
    while end < n - start and old[-1 - end] == new[-1 - end]:
        end += 1
    while start > 0 and (_splits_word(old, start) or _splits_word(new, start)):  # never cut a word in half
        start -= 1
    while end > 0 and (_splits_word(old, len(old) - end) or _splits_word(new, len(new) - end)):
        end -= 1
    old_part, new_part = old[start : len(old) - end], new[start : len(new) - end]
    if not old_part.strip() or old.count(old_part) != 1:
        raise ValueError("could not tell exactly which words changed, so the block was left as it was")
    pattern = re.compile(r"\s+".join(re.escape(word) for word in old_part.split()))
    holders = [s for s in tag.find_all(string=True) if type(s) is NavigableString and pattern.search(s)]
    if len(holders) != 1:
        raise ValueError("the change crosses a link or formatting, so it was not applied (the markup is kept)")
    holder = holders[0]
    original = NavigableString(str(holder))
    edited = NavigableString(pattern.sub(lambda _: new_part, str(holder), count=1))
    holder.replace_with(edited)
    if visible_text(tag) != new:  # safety net: never leave the block different from what was asked for
        edited.replace_with(original)
        raise ValueError("the edit did not give the requested text, so the block was left as it was")


_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
# A heading goes in front of flow content, never in front of the document skeleton or the inside of a list or table.
_NO_HEADING_BEFORE = {"html", "head", "body", "li", "dt", "dd", "tr", "td", "th", "thead", "tbody", "tfoot", "caption",
                      "summary", "option", "source", "track"} | _HEADING_TAGS


def _wrap_term(soup: BeautifulSoup, tag: Tag, term: str, explanation: str) -> None:
    """Wrap the first whole-word occurrence of `term` (inside a single text node) in <abbr title=...>.

    The visible text does not change. Raises ValueError, changing nothing, when the term is not found in one text node
    or is already explained.
    """
    pattern = re.compile(r"(?<!\w)" + re.escape(term) + r"(?!\w)")
    for node in tag.find_all(string=True):
        if type(node) is not NavigableString or any(p.name == "abbr" for p in node.parents):
            continue
        match = pattern.search(str(node))
        if match is None:
            continue
        text = str(node)
        abbr = soup.new_tag("abbr")
        abbr["title"] = explanation
        abbr.string = match.group()
        node.replace_with(NavigableString(text[: match.start()]), abbr, NavigableString(text[match.end():]))
        return
    if any(a.get_text() == term for a in tag.find_all("abbr")):
        raise ValueError(f"'{term}' is already explained")
    raise ValueError(f"'{term}' was not found in one piece of text in the block")


def _matches(current: str, expected: str) -> bool:
    return _squash(current) == _squash(expected)


def _has_rich_inline(tag: Tag) -> bool:
    return tag.find(list(_RICH_INLINE)) is not None


def _replace_button_text(soup: BeautifulSoup, tag: Tag, label: str) -> bool:
    if tag.name == "input":
        if (tag.get("type") or "").lower() not in {"button", "submit", "reset"}:
            return False
        tag["value"] = label
    else:
        text_nodes = [n for n in tag.find_all(string=True) if n.strip()]
        if text_nodes:
            text_nodes[0].replace_with(label)
            for node in text_nodes[1:]:
                node.extract()
        else:
            span = soup.new_tag("span")
            span.string = label
            tag.append(span)
    tag["aria-label"] = label
    return True


def apply_adapted_spec(html: str, spec: AdaptedUISpec) -> RenderResult:
    """Resolve every id before editing, then apply safe typed changes in order.

    A skipped change is reported by its index in ``spec.changes``. Resolving the full
    index and all menu item references up front prevents document-order ids from
    shifting underneath later structural changes.
    """
    soup = BeautifulSoup(html, "html.parser")
    index = _index_blocks(soup)
    targets = [index.get(change.block_id) for change in spec.changes]
    menu_items = {
        i: [[index.get(item_id) for item_id in group.item_ids] for group in change.groups]
        for i, change in enumerate(spec.changes)
        if change.action == "group_menu_items"
    }
    result = RenderResult(html="")

    for i, (change, tag) in enumerate(zip(spec.changes, targets)):
        if change.action == "set_style" and change.block_id == "page":
            tag = soup.body or soup.find(True)
        if tag is None or not isinstance(tag, Tag):
            result.skipped[i] = f"target '{change.block_id}' was not found"
            continue

        try:
            if change.action == "replace_text":
                _replace_text(tag, change.value)
            elif change.action == "set_style":
                old = tag.get("style", "").rstrip("; ")
                tag["style"] = f"{old}; {change.value}" if old else change.value
            elif change.action in {"text_to_list", "split_into_steps"}:
                if not _matches(visible_text(tag), change.expected_original):
                    raise ValueError("live text no longer matches expected_original")
                if _has_rich_inline(tag):
                    raise ValueError("block contains links or inline formatting; rich content was preserved by skipping")
                if change.action == "text_to_list":
                    list_tag = soup.new_tag("ul" if change.list_type == "bulleted" else "ol")
                    for item in change.items:
                        li = soup.new_tag("li")
                        li.string = item
                        list_tag.append(li)
                    tag.replace_with(list_tag)
                else:
                    replacements = []
                    if change.intro:
                        intro = soup.new_tag("p")
                        intro.string = change.intro
                        replacements.append(intro)
                    steps = soup.new_tag("ol")
                    for step in change.steps:
                        li = soup.new_tag("li")
                        li.string = step
                        steps.append(li)
                    replacements.append(steps)
                    tag.replace_with(*replacements)
            elif change.action == "add_button_label":
                if tag.name != "button" and tag.get("role") != "button":
                    raise ValueError("target is not a button")
                if change.expected_original is not None and not _matches(visible_text(tag), change.expected_original):
                    raise ValueError("live text no longer matches expected_original")
                label = soup.new_tag("span")
                label["class"] = ["genui-button-label", f"genui-button-label--{change.placement}"]
                label.string = change.label
                tag.append(label)
                tag["aria-label"] = change.label
            elif change.action == "group_menu_items":
                groups = menu_items[i]
                if any(item is None for group in groups for item in group):
                    raise ValueError("one or more menu item ids were not found")
                resolved = [item for group in groups for item in group]
                current = [child for child in tag.find_all(recursive=False) if isinstance(child, Tag)]
                if resolved != current:
                    raise ValueError("group item ids do not match the menu's current direct items in order")
                for group, items in zip(change.groups, groups):
                    heading = soup.new_tag("li" if tag.name in {"ul", "ol"} else "span")
                    heading["class"] = ["genui-menu-group-heading"]
                    heading["role"] = "presentation"
                    heading.string = group.label
                    items[0].insert_before(heading)
            elif change.action == "set_link_text":
                if tag.name != "a":
                    raise ValueError("target is not a link")
                if not _matches(visible_text(tag), change.expected_original):
                    raise ValueError("live link text no longer matches expected_original")
                _replace_text(tag, change.text)
                if tag.has_attr("aria-label"):
                    tag["aria-label"] = change.text
            elif change.action == "set_button_label":
                current = tag.get("value", "") if tag.name == "input" else visible_text(tag)
                if not _matches(current, change.expected_original):
                    raise ValueError("live button label no longer matches expected_original")
                if not _replace_button_text(soup, tag, change.label):
                    raise ValueError("target is not a supported button")
            elif change.action == "set_alt_text":
                if tag.name != "img":
                    raise ValueError("target is not an image")
                if not _matches(tag.get("alt", ""), change.expected_original):
                    raise ValueError("live alt text no longer matches expected_original")
                tag["alt"] = change.alt
            elif change.action == "add_section_heading":
                if tag.name not in {"section", "article"}:
                    raise ValueError("target is not a section or article")
                if not _matches(visible_text(tag), change.expected_original):
                    raise ValueError("live section text no longer matches expected_original")
                if tag.find(["h1", "h2", "h3", "h4", "h5", "h6"]):
                    raise ValueError("section already has a heading")
                heading = soup.new_tag(f"h{change.level}")
                heading.string = change.heading
                tag.insert(0, heading)
            elif change.action == "split_paragraph":
                if tag.name != "p":
                    raise ValueError("target is not a paragraph")
                if not _matches(visible_text(tag), change.expected_original):
                    raise ValueError("live text no longer matches expected_original")
                if _has_rich_inline(tag):
                    raise ValueError("block contains links or inline formatting; rich content was preserved by skipping")
                pieces = []
                for part in change.parts:
                    piece = soup.new_tag("p")
                    piece.attrs = {k: v for k, v in tag.attrs.items() if k != "id"}
                    piece.string = part
                    pieces.append(piece)
                tag.replace_with(*pieces)
            elif change.action == "explain_term":
                if not _matches(visible_text(tag), change.expected_original):
                    raise ValueError("live text no longer matches expected_original")
                _wrap_term(soup, tag, change.term, change.explanation)
            elif change.action == "add_heading_before":
                if tag.name in _NO_HEADING_BEFORE or tag.parent is None:
                    raise ValueError(f"a heading cannot be placed in front of a <{tag.name}>")
                if not _matches(visible_text(tag), change.expected_original):
                    raise ValueError("live text no longer matches expected_original")
                previous = tag.find_previous_sibling()
                if previous is not None and previous.name in _HEADING_TAGS:
                    raise ValueError("a heading is already in front of this block")
                heading = soup.new_tag(f"h{change.level}")
                heading.string = change.heading
                tag.insert_before(heading)
            elif change.action == "stop_autoplay":
                if tag.name not in {"video", "audio"}:
                    raise ValueError("target is not a video or audio element")
                if not tag.has_attr("autoplay"):
                    raise ValueError("the media does not autoplay")
                del tag["autoplay"]
                tag["controls"] = ""
            else:  # defensive if the union grows without renderer support
                raise ValueError(f"unsupported action '{change.action}'")
        except ValueError as exc:
            result.skipped[i] = str(exc)
            continue
        result.applied_indices.append(i)

    result.html = str(soup)
    return result
