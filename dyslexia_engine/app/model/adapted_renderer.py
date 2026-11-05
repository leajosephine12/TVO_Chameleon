"""Apply a validated AdaptedUISpec to HTML without executing arbitrary HTML or DOM operations."""
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Tag

from ..adaptation_engine import _index_blocks
from .adapted_ui_spec import AdaptedUISpec

_RICH_INLINE = {"a", "b", "strong", "i", "em", "u", "code", "mark", "abbr"}


@dataclass
class RenderResult:
    html: str
    applied_indices: list[int] = field(default_factory=list)
    skipped: dict[int, str] = field(default_factory=dict)


def _squash(text: str) -> str:
    return " ".join(text.split())


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
                tag.clear()
                tag.append(change.value)
            elif change.action == "set_style":
                old = tag.get("style", "").rstrip("; ")
                tag["style"] = f"{old}; {change.value}" if old else change.value
            elif change.action in {"text_to_list", "split_into_steps"}:
                if not _matches(tag.get_text(" ", strip=True), change.expected_original):
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
                if change.expected_original is not None and not _matches(tag.get_text(" ", strip=True), change.expected_original):
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
                if not _matches(tag.get_text(" ", strip=True), change.expected_original):
                    raise ValueError("live link text no longer matches expected_original")
                tag.clear()
                tag.append(change.text)
            elif change.action == "set_button_label":
                current = tag.get("value", "") if tag.name == "input" else tag.get_text(" ", strip=True)
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
                if not _matches(tag.get_text(" ", strip=True), change.expected_original):
                    raise ValueError("live section text no longer matches expected_original")
                if tag.find(["h1", "h2", "h3", "h4", "h5", "h6"]):
                    raise ValueError("section already has a heading")
                heading = soup.new_tag(f"h{change.level}")
                heading.string = change.heading
                tag.insert(0, heading)
            else:  # defensive if the union grows without renderer support
                raise ValueError(f"unsupported action '{change.action}'")
        except ValueError as exc:
            result.skipped[i] = str(exc)
            continue
        result.applied_indices.append(i)

    result.html = str(soup)
    return result
