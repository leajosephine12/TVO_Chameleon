"""Bucket 4 of docs/metrics-map.md: judgement metrics the model checks itself.

No code finding exists for these. The model raises them directly, labeled
evidence "model judgement / <metric_id>"; the guard in dyslexia_engine
(check_judgement_evidence) rejects ids outside this registry, and the usual
quote checks still apply — so every judgement is auditable, never free-floating.

Keys match docs/metrics.pdf; instructions are the prompt text, verbatim.
"""

# Text call (call 1)
TEXT_JUDGEMENT: dict[str, str] = {
    "T9": "A jargon or curriculum term a Grade 3-5 reader would not know and the page never defines. Quote the term in 'original'.",
    "S4": "A sentence that lists 3 or more items or steps inline instead of using a list. Quote the sentence.",
    "S6": "An instruction step that packs more than one action. Quote the step.",
    "J15": "An ambiguous reference ('this', 'it', 'the above', 'below') with no clear antecedent. Quote the phrase with a few surrounding words.",
}

# Vision call (call 2)
VISION_JUDGEMENT: dict[str, str] = {
    "J10": "An icon visibly unrelated to its label or function.",
    "N11": "No single visually dominant primary action on the page.",
    "L5": "An icon, border or focus ring whose contrast against its background looks below 3:1.",
}
