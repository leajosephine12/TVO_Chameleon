"""Rendered-page half of the metrics map: layout metrics, axe-core, screenshot.

One Playwright render serves everything: per-block computed styles (L1 L2 L3),
reflow at 320px (L6), font-family count (L12), axe with target-size enabled
(WCAG baseline + L4), a full-page PNG for model call 2, and the rendered HTML.

    collect(url)          -> raw measurements + screenshot + html   (browser I/O)
    layout_findings(m)    -> findings in the shared schema          (pure, tested)
    rendered_checks(url)  -> {"findings", "metrics", "screenshot", "html"}

Playwright is an optional dependency:  uv pip install playwright && playwright install chromium
Axe is injected from cdnjs; without network the axe step is skipped and noted.
Deferred (ponytail): L7 style variance, L8 density, L9/L10 fold checks — add when a reviewer asks.
"""
from .thresholds import THRESHOLDS, finding

AXE_URL = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js"

# Per-block measurements, same block-id convention as everywhere else ("<tag>-<n>").
_MEASURE_JS = """
() => {
  const counts = {};
  const blocks = [];
  const fonts = new Set();
  for (const el of document.querySelectorAll('*')) {
    const tag = el.tagName.toLowerCase();
    counts[tag] = (counts[tag] || 0) + 1;
    if (!['p','li','blockquote','h1','h2','h3','h4','h5','h6'].includes(tag)) continue;
    if (!el.innerText || !el.innerText.trim()) continue;
    const cs = getComputedStyle(el);
    const px = parseFloat(cs.fontSize);
    const lh = cs.lineHeight === 'normal' ? 1.2 : parseFloat(cs.lineHeight) / px;
    fonts.add(cs.fontFamily.split(',')[0].trim().toLowerCase());
    blocks.push({
      block_id: tag + '-' + counts[tag],
      kind: tag,
      font_size_px: Math.round(px * 10) / 10,
      line_height: Math.round(lh * 100) / 100,
      line_length_chars: Math.round(el.clientWidth / (px * 0.5)),
      text_align: cs.textAlign,
    });
  }
  return { blocks, font_families: [...fonts] };
}
"""


def layout_findings(m: dict) -> list[dict]:
    """Measurements -> findings. Pure; `m` is what collect() returns (minus screenshot)."""
    out: list[dict] = []
    prose = [b for b in m["blocks"] if b["kind"] in ("p", "li", "blockquote")]

    for b in prose:
        if b["line_length_chars"] > THRESHOLDS["L1"]["max_chars"]:
            out.append(finding("L1", b["block_id"], {"line_length_chars": b["line_length_chars"]},
                               f"~{b['line_length_chars']} characters per line."))
        if b["line_height"] < THRESHOLDS["L2"]["min_line_height"] or b["text_align"] == "justify":
            out.append(finding("L2", b["block_id"],
                               {"line_height": b["line_height"], "text_align": b["text_align"]},
                               f"Line height {b['line_height']}" + (", justified text" if b["text_align"] == "justify" else ".")))
        if b["font_size_px"] < THRESHOLDS["L3"]["min_px"]:
            out.append(finding("L3", b["block_id"], {"font_size_px": b["font_size_px"]},
                               f"Body text is {b['font_size_px']}px."))

    if m.get("scroll_width_320") and m["scroll_width_320"] > THRESHOLDS["L6"]["viewport_px"]:
        out.append(finding("L6", "page", {"scroll_width_320": m["scroll_width_320"]},
                           f"Page is {m['scroll_width_320']}px wide at a 320px viewport (2-D scrolling)."))

    if len(m.get("font_families", [])) > THRESHOLDS["L12"]["max_font_families"]:
        out.append(finding("L12", "page", {"font_families": m["font_families"]},
                           f"{len(m['font_families'])} font families."))

    for v in m.get("axe_violations", []):
        out.append(finding("L4" if v["id"] == "target-size" else "AXE",
                           v.get("selector", "page"),
                           {"rule_id": v["id"], "impact": v.get("impact")},
                           v.get("description", v["id"])))
    return out


def collect(url: str, timeout_ms: int = 30000) -> dict:
    """Render `url` once and return measurements, axe violations, screenshot (PNG bytes) and html."""
    from playwright.sync_api import sync_playwright  # optional dep, imported lazily

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        # bypass_csp: a captured page is served with a policy that blocks every script. Under it the axe
        # script tag never loads and never fails, so add_script_tag would wait forever.
        page = browser.new_page(viewport={"width": 1280, "height": 900}, bypass_csp=True)
        page.goto(url, timeout=timeout_ms, wait_until="networkidle")
        m = page.evaluate(_MEASURE_JS)
        m["axe_violations"], m["axe_error"] = [], None
        try:
            page.add_script_tag(url=AXE_URL)
            raw = page.evaluate("() => axe.run(document, {rules: {'target-size': {enabled: true}}})")
            m["axe_violations"] = [
                {"id": v["id"], "impact": v.get("impact"), "description": v.get("help", ""),
                 "selector": (v["nodes"][0]["target"][0] if v.get("nodes") else "page")}
                for v in raw["violations"]
            ]
        except Exception as e:  # no network / CSP: measurements still ship, the gap is named
            m["axe_error"] = f"axe skipped: {e}"
        screenshot = page.screenshot(full_page=True, type="png")
        html = page.content()
        page.set_viewport_size({"width": THRESHOLDS["L6"]["viewport_px"], "height": 900})
        m["scroll_width_320"] = page.evaluate("() => document.documentElement.scrollWidth")
        browser.close()
    return {**m, "screenshot": screenshot, "html": html}


def rendered_checks(url: str) -> dict:
    """The one-call version: findings + metrics (for model call 2) + screenshot + html."""
    m = collect(url)
    screenshot, html = m.pop("screenshot"), m.pop("html")
    return {"findings": layout_findings(m), "metrics": m, "screenshot": screenshot, "html": html}
