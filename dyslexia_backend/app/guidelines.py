"""Level 1 guidelines: adapt the *representation* of the content.

Single source of truth. Every number the engine applies comes from here, and
the same list is exposed over MCP so the AI model can cite the rule it applied.
"""
from .schemas import Guideline

# ---- Tunable values derived from the research -------------------------------
FONT_STACK = "Verdana, Tahoma, Arial, Calibri, sans-serif"
BODY_FONT_PX = 18                       # research: 16-19px (12-14pt)
HEADING_SCALE = {                       # research: headings >= 20% larger than body
    "h1": 1.8, "h2": 1.5, "h3": 1.3, "h4": 1.2, "h5": 1.2, "h6": 1.2,
}
AVG_LETTER_WIDTH_EM = 0.5               # assumption: average glyph width in sans-serif
LETTER_SPACING_EM = round(0.35 * AVG_LETTER_WIDTH_EM, 3)   # 35% of letter width
WORD_SPACING_EM = round(3.5 * LETTER_SPACING_EM, 3)        # 3.5x character spacing
LINE_HEIGHT = 1.6                       # research: at least 1.5
MAX_LINE_CH = 65                        # research: 60-70 characters
BG_COLOR = "#FAF3E0"                    # cream, single colour, no high contrast
TEXT_COLOR = "#3A3A3A"                  # soft dark grey instead of pure black
LINK_COLOR = "#1F4E79"

LEVEL1_GUIDELINES: list[Guideline] = [
    Guideline(id="L1.1.1", level=1, category="Distortion of text", title="Sans-serif font",
              rule="Use sans-serif fonts like Arial, Calibri, Verdana or Tahoma.",
              params={"font_family": FONT_STACK}),
    Guideline(id="L1.1.2", level=1, category="Distortion of text", title="Font size",
              rule="Use 12 to 14 point (16 to 19 pixels).",
              params={"font_size_px": BODY_FONT_PX}),
    Guideline(id="L1.1.3", level=1, category="Distortion of text", title="Heading size",
              rule="Headings must be at least 20% larger than body text.",
              params={"heading_scale": HEADING_SCALE}),
    Guideline(id="L1.1.4", level=1, category="Distortion of text", title="Letter spacing",
              rule="Inter-character spacing is about 35% of the average letter width.",
              params={"letter_spacing_em": LETTER_SPACING_EM, "assumed_avg_letter_width_em": AVG_LETTER_WIDTH_EM}),
    Guideline(id="L1.1.5", level=1, category="Distortion of text", title="Word spacing",
              rule="Inter-word spacing is at least 3.5 times the character spacing.",
              params={"word_spacing_em": WORD_SPACING_EM}),
    Guideline(id="L1.1.6", level=1, category="Distortion of text", title="Line spacing",
              rule="Use at least 1.5 spacing between lines.",
              params={"line_height": LINE_HEIGHT}),
    Guideline(id="L1.1.7", level=1, category="Distortion of text", title="No underline or italics",
              rule="Avoid underlines and italics. Use bold for emphasis instead.",
              params={"replace_with": "strong"}),
    Guideline(id="L1.2.1", level=1, category="Dyslexia friendly colour", title="No high contrast",
              rule="Avoid stark black on white. Use soft dark text.",
              params={"text_color": TEXT_COLOR}),
    Guideline(id="L1.2.2", level=1, category="Dyslexia friendly colour", title="Single colour background",
              rule="Use one off-white, cream, light grey or soft pastel background.",
              params={"background": BG_COLOR}),
    Guideline(id="L1.3.1", level=1, category="Layout", title="No columns",
              rule="Avoid multi-column page layouts.",
              params={"column_count": 1}),
    Guideline(id="L1.3.2", level=1, category="Layout", title="Line length",
              rule="Keep lines to roughly 60 to 70 characters.",
              params={"max_width_ch": MAX_LINE_CH}),
]


def get_guidelines(level: int) -> list[Guideline]:
    return [g for g in LEVEL1_GUIDELINES if g.level == level]


# ---- Colour helpers ----------------------------------------------------------
def _luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast_ratio(fg: str, bg: str) -> float:
    a, b = _luminance(fg), _luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return round((hi + 0.05) / (lo + 0.05), 2)


# ---- Page-wide recommendations ----------------------------------------------
# Each is ONE recommendation the user can accept or deny, backed by one CSS section.
PAGE_RULES: dict[str, dict] = {
    "typography": {
        "guidelines": "L1.1.1, L1.1.2, L1.1.3",
        "suggestion": (f"Use a sans-serif font (Verdana, Tahoma, Arial), {BODY_FONT_PX}px body text, "
                       "and headings 1.2 to 1.8 times larger than body text."),
        "rationale": "Sans-serif fonts at 16 to 19px are less crowded; headings need to be at least 20% larger than body text.",
    },
    "spacing": {
        "guidelines": "L1.1.4, L1.1.5, L1.1.6",
        "suggestion": (f"Letter spacing {LETTER_SPACING_EM}em, word spacing {WORD_SPACING_EM}em, "
                       f"line height {LINE_HEIGHT}."),
        "rationale": "Wider letter, word and line spacing reduces visual crowding. Line spacing should be at least 1.5.",
    },
    "color": {
        "guidelines": "L1.2.1, L1.2.2",
        "suggestion": f"Cream background ({BG_COLOR}) with soft dark grey text ({TEXT_COLOR}), no stark black on white.",
        "rationale": "High contrast and bright white backgrounds can make text appear to shimmer. One soft background colour is easier to read.",
    },
    "layout": {
        "guidelines": "L1.3.1, L1.3.2",
        "suggestion": f"Single column layout with lines of about {MAX_LINE_CH} characters.",
        "rationale": "Columns make it easy to lose your place. Line length of 60 to 70 characters is ideal.",
    },
    "emphasis": {
        "guidelines": "L1.1.7",
        "suggestion": "Remove italics and underlines set by the page's CSS and use bold for emphasis.",
        "rationale": "Italics and underlines make words look closer together and more cramped.",
    },
}


def _typography() -> str:
    headings = "\n".join(f"h{i} {{ font-size: {HEADING_SCALE[f'h{i}']}em !important; }}" for i in range(1, 7))
    return f"""/* typography: L1.1.1, L1.1.2, L1.1.3 */
html, body {{ font-family: {FONT_STACK} !important; font-size: {BODY_FONT_PX}px !important; }}
body * {{ font-family: inherit !important; }}
p, li, dd, dt, td, th, blockquote, label, span, a, div {{ font-size: 1em !important; }}
{headings}
"""


def _spacing() -> str:
    return f"""/* spacing: L1.1.4, L1.1.5, L1.1.6 */
html, body {{
  line-height: {LINE_HEIGHT} !important;
  letter-spacing: {LETTER_SPACING_EM}em !important;
  word-spacing: {WORD_SPACING_EM}em !important;
}}
body * {{ line-height: inherit !important; }}
"""


def _color() -> str:
    return f"""/* color: L1.2.1, L1.2.2 */
html, body {{ background: {BG_COLOR} !important; color: {TEXT_COLOR} !important; }}
body * {{ background-color: transparent !important; color: inherit !important; }}
a {{ color: {LINK_COLOR} !important; }}
"""


def _layout() -> str:
    return f"""/* layout: L1.3.1, L1.3.2 */
body * {{ column-count: 1 !important; columns: auto !important; }}
p, li, dd, blockquote {{ max-width: {MAX_LINE_CH}ch !important; }}
"""


def _emphasis() -> str:
    return """/* emphasis: L1.1.7 */
body * { font-style: normal !important; text-decoration: none !important; }
b, strong, th, a { font-weight: 700 !important; }
"""


_SECTION_CSS = {
    "typography": _typography, "spacing": _spacing, "color": _color,
    "layout": _layout, "emphasis": _emphasis,
}


def css_for(sections: list[str]) -> str:
    """Stylesheet for only the accepted page-wide sections (stable order)."""
    return "\n".join(_SECTION_CSS[s]() for s in PAGE_RULES if s in sections)