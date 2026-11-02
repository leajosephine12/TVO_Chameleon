"""One THRESHOLDS dict keyed by metric ID (docs/metrics-map.md convention).

Tier and source come from docs/metrics.pdf. The PDF's "Calibrate? = Yes" rows
are the values teachers/testers will tune — never inline these numbers in checks.
"""

THRESHOLDS: dict[str, dict] = {
    # --- text (analyze_text) ---
    "T1": {"tier": "C", "max_grade": 6.0, "max_formula_gap": 2.0,
           "threshold": "target Grade 3-6 on prose blocks; flag if formulas differ by > 2 grades",
           "source": "Kincaid et al. 1975 / WCAG 3.1.5 (AAA)"},
    "T2": {"tier": "C", "max_score": 5.9,
           "threshold": "Dale-Chall <= 5.9 (grade 5-6)",
           "source": "Dale-Chall readability formula"},
    "T3": {"tier": "C", "max_words": 25, "ideal": "15-20",
           "threshold": "flag > 25 words; ideal 15-20",
           "source": "GOV.UK 25-word sentence limit"},
    "T4": {"tier": "C", "max_conjunctions": 2,
           "threshold": "<= 2 conjunctions per sentence",
           "source": "WCAG technique G153"},
    "T6": {"tier": "C", "report_only": True,
           "threshold": "report passive-voice sentences; no sourced number",
           "source": "digital.gov plain language"},
    "T7": {"tier": "C", "max_rare_pct": 10.0,
           "threshold": "flag > 10% tokens outside Dale-Chall familiar words, proper nouns excluded",
           "source": "W3C COGA Making Content Usable (2021)"},
    "S1": {"tier": "C", "max_words": 50, "max_sentences": 5,
           "threshold": "flag > 50 words (COGA) or > 5 sentences (Ontario.ca)",
           "source": "W3C COGA / Ontario.ca Style Guide"},
    # --- structure (structure_checks) ---
    "S2": {"tier": "C", "words_per_heading": 200,
           "threshold": ">= 1 heading per ~200 words",
           "source": "Canada.ca Content Style Guide"},
    "S3": {"tier": "C",
           "threshold": "every content section has a heading",
           "source": "WCAG 2.4.10 Section Headings (AAA)"},
    "S5": {"tier": "C", "max_items": 7, "max_sentences_per_item": 1,
           "threshold": "<= 7 items; one sentence per item",
           "source": "Canada.ca Content Style Guide"},
    "T8": {"tier": "D",
           "threshold": "all-caps token with no <abbr> and no expansion at first use: 0 allowed",
           "source": "WCAG 3.1.4 Abbreviations (AAA)"},
    "J5": {"tier": "C", "stoplist": ["click here", "more", "here", "read more"],
           "threshold": "generic link text: 0 allowed",
           "source": "WCAG 2.4.4 Link Purpose (A)"},
    "J11": {"tier": "C",
            "threshold": "control whose only content is an image/SVG: flag all",
            "source": "W3C COGA Making Content Usable (2021)"},
    "J12": {"tier": "D", "stoplist": ["image", "picture", "photo", "icon", "graphic"],
            "threshold": "alt equals filename, generic word, or empty on informative image",
            "source": "WCAG 1.1.1 Non-text Content (A)"},
    "J14": {"tier": "D", "stoplist": ["submit", "ok", "go"],
            "threshold": "vague button label instead of verb + object",
            "source": "W3C COGA / GOV.UK Design System: Button"},
    "N1": {"tier": "C",
           "threshold": "aria-current or highlighted nav item present",
           "source": "WCAG 2.4.8 Location (AAA)"},
    "N2": {"tier": "C", "min_depth": 3,
           "threshold": "breadcrumb (nav + ol + aria-current) present when URL depth >= 3",
           "source": "WCAG 2.4.8 Location (AAA) / USWDS Breadcrumb"},
    "N3": {"tier": "D", "min_ways": 2,
           "threshold": ">= 2 of: nav, search, sitemap, related links, table of contents",
           "source": "WCAG 2.4.5 Multiple Ways (AA)"},
    "N6": {"tier": "F", "max_primary_navs": 1,
           "threshold": "more than one primary nav landmark: flag",
           "source": "NN/g Children's websites usability"},
    "N7": {"tier": "F",
           "threshold": "in-site Back/Home control visible on every page",
           "source": "NN/g Children's websites usability / WCAG 3.0 WD 'return to start'"},
    "N8": {"tier": "F", "max_depth": 2, "max_links": 6,
           "threshold": "<= 2 menu tiers; <= 6 links per dropdown",
           "source": "NN/g Menu design"},
    "L11": {"tier": "C",
            "threshold": "every icon has adjacent text",
            "source": "Large & Beheshti, children's web portal guidelines"},
    "M1": {"tier": "D",
           "threshold": "autoplaying media needs a pause/stop/hide control",
           "source": "WCAG 2.2.2 Pause, Stop, Hide (A)"},
    "M2": {"tier": "D", "max_frames": 5,
           "threshold": "<= 5 frames; no auto-advance",
           "source": "NN/g Designing effective carousels"},
}


def finding(metric_id: str, block_id: str, measured: dict, detail: str) -> dict:
    """One finding in the shared schema; threshold/source/tier copied from THRESHOLDS."""
    t = THRESHOLDS[metric_id]
    f = {
        "metric_id": metric_id,
        "block_id": block_id,
        "measured": measured,
        "threshold": t["threshold"],
        "source": t["source"],
        "tier": t["tier"],
        "detail": detail,
    }
    if t.get("report_only"):
        f["report_only"] = True
    return f
