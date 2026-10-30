"""Chameleon MCP server (Interface 2: Backend <-> MCP).

Deterministic page-analysis tools. No model inside — the backend calls the
model (Claude API now, local OpenAI-compatible later) and feeds it these
tool results.

All tools currently return fixed mock JSON so the backend/UI can integrate
against the real shapes. Real implementations land tool by tool.

Shared recommendation contract (built by the BACKEND from these findings,
documented here so the team has one reference):

    {
      "id": "r12",
      "block_id": "p-4",
      "type": "long_sentence",
      "original": "…",
      "suggestion": "…",
      "rationale": "34 words; Grade 3-5 target <= 15-20",
      "evidence": "readability tool / W3C COGA",
      "severity": "medium",
      "status": "pending"
    }
"""

import os

from fastmcp import FastMCP

mcp = FastMCP("chameleon-tools")

# Shared finding schema (see docs/metrics-map.md): every code-derived issue is
#   {metric_id, block_id | selector, measured, threshold, source, detail}
# so the model can copy real numbers into rationale/evidence instead of
# inventing them.

# Mock page content shared across tools so the pipeline is consistent:
# p-2 is deliberately a long, hard sentence that analyze_text flags.
# "kind" tags the element type — T-metrics run on prose ("p") blocks only.
MOCK_BLOCKS = [
    {
        "id": "h-1",
        "kind": "h1",
        "selector": "main > h1",
        "text": "Course Portal",
    },
    {
        "id": "p-1",
        "kind": "p",
        "selector": "main > p:nth-of-type(1)",
        "text": "Welcome to the course portal.",
    },
    {
        "id": "p-2",
        "kind": "p",
        "selector": "main > p:nth-of-type(2)",
        "text": (
            "In order to successfully complete the registration procedure, "
            "students are required to navigate to the enrollment section, "
            "locate the appropriate course offering, and subsequently confirm "
            "their selection before the deadline elapses."
        ),
    },
]


@mcp.tool
def fetch_page(url: str) -> dict:
    """Fetch a web page and return its text blocks (with stable IDs and CSS
    selectors) plus a base64 screenshot. MOCK: returns fixed blocks,
    screenshot is null."""
    # ponytail: mock. Real version: Playwright (render + screenshot) or httpx+BeautifulSoup (text only).
    return {"url": url, "blocks": MOCK_BLOCKS, "screenshot_b64": None}


@mcp.tool
def analyze_text(blocks: list[dict]) -> dict:
    """Analyze text blocks for dyslexia-relevant issues: long sentences,
    readability scores, difficult words. MOCK: returns fixed findings for
    the mock page."""
    # ponytail: mock. Real version: textstat + a word-frequency list.
    return {
        "findings": [
            {
                "metric_id": "T3",
                "block_id": "p-2",
                "measured": {"word_count": 34},
                "threshold": "flag > 25 words; ideal 15-20",
                "source": "GOV.UK sentence-length limit",
                "detail": "Sentence has 34 words.",
            },
            {
                "metric_id": "T7",
                "block_id": "p-2",
                "measured": {"rare_words": ["procedure", "subsequently", "elapses"], "rare_pct": 14.7},
                "threshold": "flag > 10% tokens outside common-word list",
                "source": "W3C COGA / Dale-Chall 3000 familiar words",
                "detail": "Low-frequency vocabulary.",
            },
            {
                "metric_id": "T1",
                "block_id": "p-2",
                "measured": {"flesch_kincaid_grade": 14.2},
                "threshold": "target Grade 3-6 on prose blocks",
                "source": "Kincaid et al. 1975 / textstat",
                "detail": "Reads at Grade 14.",
            },
        ]
    }


@mcp.tool
def run_axe(url: str) -> dict:
    """Run axe-core WCAG checks against a page. MOCK: returns fixed findings."""
    # ponytail: mock. Real version: Playwright + axe-core script injection.
    return {
        "url": url,
        "violations": [
            {
                "rule_id": "color-contrast",
                "impact": "serious",
                "selector": "main > p:nth-of-type(2)",
                "description": "Element has insufficient color contrast of 2.9 (foreground: #999999, background: #ffffff). Expected 4.5:1.",
            }
        ],
    }


@mcp.tool
def structure_checks(url: str) -> dict:
    """Static DOM checks (no browser): heading density, list length, generic
    link text, icon-only controls, breadcrumbs, nav landmarks, autoplay.
    MOCK: returns fixed findings."""
    # ponytail: mock. Real version: httpx + BeautifulSoup over the DOM.
    return {
        "url": url,
        "findings": [
            {
                "metric_id": "J5",
                "selector": "main a:nth-of-type(3)",
                "measured": {"link_text": "click here"},
                "threshold": "0 allowed",
                "source": "WCAG 2.4.4 Link Purpose",
                "detail": "Generic link text.",
            },
            {
                "metric_id": "S2",
                "selector": "main",
                "measured": {"words": 450, "headings": 1},
                "threshold": ">= 1 heading per ~200 words",
                "source": "W3C COGA",
                "detail": "450 words under a single heading.",
            },
        ],
    }


@mcp.tool
def layout_metrics(url: str) -> dict:
    """Measure layout from the DOM: font size, line spacing, line length.
    MOCK: returns fixed metrics."""
    # ponytail: mock. Real version: Playwright + getComputedStyle in the page.
    return {
        "url": url,
        "font_size_px": 14,
        "line_height": 1.2,
        "avg_line_length_chars": 95,
    }


if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
