"""Level 1 adaptation engine: pure Python, no MCP, no network.

analyze_level1(html)                    -> list[Recommendation]  (nothing is changed)
apply_level1(html, recommendations)     -> AdaptResult           (only accepted/edited ones)

Block ids are "<tag>-<n>": the n-th <tag> in document order (1-based), e.g. "p-4".
They are resolved against the HTML you pass in, so send the same HTML to both calls.
"""
import re
from collections import Counter

from bs4 import BeautifulSoup, Tag

from .guidelines import BG_COLOR, PAGE_RULES, TEXT_COLOR, contrast_ratio, css_for
from .schemas import AdaptResult, Recommendation

MARKER = "data-dyslexia-adapt"
ITALIC_TAGS = {"i", "em", "cite", "dfn"}
ELEMENT_TYPES = {"italic_text", "underline_text", "inline_style"}

_BAD_INLINE = re.compile(
    r"(font-style\s*:\s*(italic|oblique)"
    r"|text-decoration[^;]*underline"
    r"|column-count\s*:\s*(?!1\b|auto)\d+"
    r"|columns\s*:\s*(?!auto)\d+)",
    re.I,
)
# Page-wide problems we can detect in the page's own CSS (used to raise severity).
_DETECT = {
    "typography": re.compile(r"\b(times|georgia|garamond)\b|font-family\s*:\s*serif|font-size\s*:\s*(1[0-5]|[0-9])px", re.I),
    "layout": re.compile(r"column-count\s*:\s*[2-9]|columns\s*:\s*[2-9]", re.I),
    "emphasis": re.compile(r"font-style\s*:\s*italic|text-decoration[^;]*underline", re.I),
}
_BLACK_ON_WHITE = (
    re.compile(r"background(-color)?\s*:\s*(#fff(fff)?|white)\b", re.I),
    re.compile(r"(?<![-\w])color\s*:\s*(#000(000)?|black)\b", re.I),
)


def _index_blocks(soup: BeautifulSoup) -> dict[str, Tag]:
    counts: Counter = Counter()
    index: dict[str, Tag] = {}
    for tag in soup.find_all(True):
        counts[tag.name] += 1
        index[f"{tag.name}-{counts[tag.name]}"] = tag
    return index


def _clean_style(style: str) -> str:
    kept = [d.strip() for d in style.split(";") if d.strip() and not _BAD_INLINE.search(d)]
    return "; ".join(kept)


def _adapted_marker(soup: BeautifulSoup) -> Tag | None:
    return soup.find("style", attrs={MARKER: True})


def _applied_sections(soup: BeautifulSoup) -> set[str]:
    m = _adapted_marker(soup)
    return set(filter(None, m.get("data-sections", "").split(","))) if m else set()


def analyze_level1(html: str) -> list[Recommendation]:
    soup = BeautifulSoup(html, "html.parser")
    recs: list[Recommendation] = []

    def add(**kw) -> None:
        recs.append(Recommendation(id=f"r{len(recs) + 1}", status="pending", **kw))

    # --- element-level: one recommendation per offending element -------------
    for block_id, tag in _index_blocks(soup).items():
        if tag.name in ITALIC_TAGS:
            add(block_id=block_id, type="italic_text", original=str(tag),
                suggestion=f"<strong>{tag.decode_contents()}</strong>",
                rationale="Italics make words look closer together and more cramped. Use bold for emphasis instead.",
                evidence="Level 1 guideline L1.1.7", severity="low")
        elif tag.name == "u":
            add(block_id=block_id, type="underline_text", original=str(tag),
                suggestion=tag.decode_contents(),
                rationale="Underlines make words look closer together. Use bold for emphasis instead.",
                evidence="Level 1 guideline L1.1.7", severity="low")
        if tag.has_attr("style") and _BAD_INLINE.search(tag["style"]):
            add(block_id=block_id, type="inline_style", original=tag["style"],
                suggestion=_clean_style(tag["style"]),
                rationale="This inline style uses italics, underline or columns, which the dyslexia guidelines avoid.",
                evidence="Level 1 guidelines L1.1.7, L1.3.1", severity="medium")

    # --- page-wide: one recommendation per rule group -------------------------
    css_text = "" if _adapted_marker(soup) else " ".join(s.get_text() for s in soup.find_all("style"))
    done = _applied_sections(soup)
    for rule_type, rule in PAGE_RULES.items():
        if rule_type in done:
            continue
        detected = _DETECT.get(rule_type)
        found = detected.search(css_text) if detected else None
        if rule_type == "color" and all(p.search(css_text) for p in _BLACK_ON_WHITE):
            found = True
        add(block_id="page", type=rule_type,
            original=(f"Detected in page CSS: {found.group(0)}" if hasattr(found, "group")
                      else "Black text on a white background" if found
                      else "Page styling as authored (not checked against computed browser styles)"),
            suggestion=rule["suggestion"], rationale=rule["rationale"],
            evidence=f"Level 1 guidelines {rule['guidelines']}",
            severity="high" if found else "medium")
    return recs


def apply_level1(html: str, recommendations: list[Recommendation]) -> AdaptResult:
    soup = BeautifulSoup(html, "html.parser")
    index = _index_blocks(soup)          # resolve ids BEFORE any edit changes the counts
    applied: list[str] = []
    skipped: list[str] = []
    sections: set[str] = set()

    for r in recommendations:
        if r.status not in ("accepted", "edited"):
            continue
        if r.type in PAGE_RULES:
            sections.add(r.type)
            applied.append(r.id)
            continue
        tag = index.get(r.block_id)
        if r.type not in ELEMENT_TYPES or tag is None or tag.parent is None:
            skipped.append(r.id)
            continue

        edited = r.status == "edited"
        if r.type == "inline_style":
            new_style = r.suggestion if edited else _clean_style(tag["style"])
            if new_style:
                tag["style"] = new_style
            else:
                del tag["style"]
        elif edited:                      # user rewrote the replacement HTML
            fresh = BeautifulSoup(r.suggestion, "html.parser")
            tag.replace_with(*list(fresh.contents))
        elif r.type == "italic_text":
            tag.name = "strong"
        else:                             # underline_text
            tag.unwrap()
        applied.append(r.id)

    # page-wide rules: merge with anything applied in an earlier round
    previous = _adapted_marker(soup)
    if previous is not None:
        sections |= _applied_sections(soup)
        previous.decompose()
    css = css_for(sorted(sections))
    if css:
        style = soup.new_tag("style")
        style[MARKER] = "level1"
        style["data-sections"] = ",".join(s for s in PAGE_RULES if s in sections)
        style.string = css
        if soup.head:
            soup.head.append(style)
        else:                              # iframe content is often just a fragment
            soup.insert(0, style)

    return AdaptResult(
        adapted_html=str(soup),
        injected_css=css,
        applied=applied,
        skipped=skipped,
        contrast_ratio=contrast_ratio(TEXT_COLOR, BG_COLOR) if "color" in sections else None,
    )