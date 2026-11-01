"""structure_checks: static DOM checks (BeautifulSoup, no browser).

Covers the metrics-map S/J/N/L/M rows that need only the DOM:
S2 S3 S5 T8 J5 J11 J12 J14 N1 N2 N3 N6 N7 N8 L11 M1 M2.

Input:  html (the same HTML the engine analyzes), optional url (only N2 needs it).
Output: {"findings": [...]} in the shared schema. Block ids are "<tag>-<n>"
        (document order, same convention as dyslexia_engine); page-wide rows use "page".
"""
import posixpath
import re
from collections import Counter
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

from .text_metrics import split_sentences
from .thresholds import THRESHOLDS, finding

MAX_PER_METRIC = 10  # cap repeated findings so one bad pattern doesn't flood the reviewer

_HEADINGS = ["h1", "h2", "h3", "h4", "h5", "h6"]
_ABBR_TOKEN = re.compile(r"\b[A-Z]{2,}\b")


def _index(soup: BeautifulSoup) -> dict[Tag, str]:
    counts: Counter = Counter()
    ids: dict[Tag, str] = {}
    for tag in soup.find_all(True):
        counts[tag.name] += 1
        ids[tag] = f"{tag.name}-{counts[tag.name]}"
    return ids


def _text(tag: Tag) -> str:
    return tag.get_text(" ", strip=True)


def structure_checks(html: str, url: str | None = None) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    ids = _index(soup)
    findings: list[dict] = []
    body = soup.body or soup

    seen_pairs: set[tuple[str, str]] = set()

    def add(metric_id, tag, measured, detail):
        block_id = ids.get(tag, "page") if tag is not None else "page"
        if (metric_id, block_id) in seen_pairs:  # e.g. a button holding several SVGs
            return
        seen_pairs.add((metric_id, block_id))
        if sum(1 for f in findings if f["metric_id"] == metric_id) < MAX_PER_METRIC:
            findings.append(finding(metric_id, block_id, measured, detail))

    page_text = _text(body)
    words = len(page_text.split())

    # S2 heading density
    headings = body.find_all(_HEADINGS)
    if words and len(headings) < words / THRESHOLDS["S2"]["words_per_heading"]:
        add("S2", None, {"words": words, "headings": len(headings)},
            f"{words} words under {len(headings)} heading(s).")

    # S3 content section without a heading
    for sec in body.find_all(["section", "article"]):
        if not sec.find(_HEADINGS) and len(_text(sec).split()) > 20:
            add("S3", sec, {"words": len(_text(sec).split())}, "Content section has no heading.")

    # S5 list length / list items with several sentences
    for lst in body.find_all(["ul", "ol"]):
        items = lst.find_all("li", recursive=False)
        if len(items) > THRESHOLDS["S5"]["max_items"]:
            add("S5", lst, {"items": len(items)}, f"List has {len(items)} items.")
        for li in items:
            n = len(split_sentences(_text(li)))
            if n > THRESHOLDS["S5"]["max_sentences_per_item"]:
                add("S5", li, {"sentences": n}, f"List item has {n} sentences.")

    # T8 unexplained abbreviations
    explained = {a.get_text(strip=True) for a in body.find_all("abbr")}
    seen: set[str] = set()
    for token in _ABBR_TOKEN.findall(page_text):
        if token in explained or token in seen:
            continue
        seen.add(token)
        # expansion at first use: "NASA (National ...)" or "(NASA)" right after the long form
        if re.search(re.escape(token) + r"\s*\(", page_text) or re.search(r"\(\s*" + re.escape(token) + r"\s*\)", page_text):
            continue
        add("T8", None, {"abbreviation": token}, f"'{token}' is never expanded.")

    # J5 generic link text
    for a in body.find_all("a"):
        label = _text(a).lower().rstrip(".!")
        if label in THRESHOLDS["J5"]["stoplist"]:
            add("J5", a, {"link_text": label}, "Generic link text.")

    # J11 icon-only control / L11 icon without adjacent text
    for el in body.find_all(["img", "svg"]):
        holder = el.find_parent(["a", "button"])
        if holder is not None:
            if not _text(holder):
                add("J11", holder, {"control": holder.name}, "Control's only content is an image.")
        elif el.parent is not None and not _text(el.parent):
            add("L11", el, {"element": el.name}, "Icon has no adjacent text.")

    # J12 alt text quality
    for img in body.find_all("img"):
        alt = (img.get("alt") or "").strip()
        src_name = posixpath.splitext(posixpath.basename(urlparse(img.get("src") or "").path))[0]
        if alt.lower() in THRESHOLDS["J12"]["stoplist"] or (alt and alt == src_name):
            add("J12", img, {"alt": alt}, "Alt text is a filename or generic word.")

    # J14 vague button label
    for btn in body.find_all("button") + body.select('input[type="submit"]') + body.select('[role="button"]'):
        label = (_text(btn) if btn.name != "input" else (btn.get("value") or "")).strip().lower()
        if label in THRESHOLDS["J14"]["stoplist"]:
            add("J14", btn, {"label": label}, f"Button says only '{label}'.")

    # Navigation metrics (page-level)
    navs = [n for n in body.find_all("nav") if not n.find_parent("footer")]
    if navs:
        # N1 location cue
        if not body.select("[aria-current]") and not body.select("nav .active, nav .current"):
            add("N1", None, {"navs": len(navs)}, "No aria-current or highlighted nav item.")
        # N6 single navigation system
        if len(navs) > THRESHOLDS["N6"]["max_primary_navs"]:
            add("N6", None, {"navs": len(navs)}, f"{len(navs)} navigation landmarks.")
        # N8 dropdown depth and size
        for nav in navs:
            for ul in nav.find_all("ul"):
                depth = len(ul.find_parents("ul", limit=3)) + 1
                links = ul.find_all("li", recursive=False)
                if depth > THRESHOLDS["N8"]["max_depth"]:
                    add("N8", ul, {"depth": depth}, f"Menu nested {depth} tiers deep.")
                elif depth > 1 and len(links) > THRESHOLDS["N8"]["max_links"]:
                    add("N8", ul, {"links": len(links)}, f"Dropdown holds {len(links)} links.")

    # N2 breadcrumb on deep pages (needs the URL)
    if url and len([p for p in urlparse(url).path.split("/") if p]) >= THRESHOLDS["N2"]["min_depth"]:
        if not any(n.find("ol") for n in body.find_all("nav")):
            add("N2", None, {"url_depth": len([p for p in urlparse(url).path.split("/") if p])},
                "Deep page has no breadcrumb.")

    # N3 multiple ways to find a page
    ways = sum([
        bool(navs),
        bool(body.select('input[type="search"]') or body.select('input[name*="search"], input[name="q"]')),
        bool(body.select('a[href*="sitemap"]')),
        "table of contents" in page_text.lower(),
    ])
    if ways < THRESHOLDS["N3"]["min_ways"]:
        add("N3", None, {"ways": ways}, f"Only {ways} way(s) to find pages.")

    # N7 in-site Back/Home control
    if not any(_text(a).strip().lower() in ("home", "back") or a.get("href") in ("/", "index.html")
               for a in body.find_all("a")):
        add("N7", None, {}, "No visible Home or Back link.")

    # M1 autoplay without pause control
    for media in body.select("video[autoplay], audio[autoplay]"):
        if not media.has_attr("controls"):
            add("M1", media, {"element": media.name}, "Autoplaying media without controls.")

    # M2 carousel heuristic
    for el in body.select('[class*="carousel"], [class*="slider"], [class*="swiper"], [class*="slideshow"]'):
        slides = el.find_all(recursive=False)
        auto = any("autoplay" in str(v).lower() for v in el.attrs.values())
        if len(slides) > THRESHOLDS["M2"]["max_frames"] or auto:
            add("M2", el, {"frames": len(slides), "auto_advance": auto}, "Carousel is long or auto-advances.")

    return {"findings": findings}
