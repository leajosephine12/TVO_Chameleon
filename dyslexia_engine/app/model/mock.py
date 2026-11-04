"""Mock model: returns fixed, valid JSON so the UI and backend can be built without a model.

The recommendations match the sample TVO blocks (p-1, p-2) in the tests/samples. All numbers
are FAKE sample data, not from a real analysis.
"""
import json

from .sample_data import SAMPLE_BLOCKS

_TEXT = {
    "recommendations": [
        {
            "id": "r1",
            "block_id": "p-1",
            "type": "long_sentence",
            "original": (
                "Students compare different ways that consumers can get value for their money when "
                "spending, such as using reward programs or taking advantage of sales."
            ),
            "suggestion": (
                "Students compare different ways that consumers can get value for their money. "
                "Examples are using reward programs or taking advantage of sales."
            ),
            "rationale": "24 words; Grade 3-5 target <= 15-20",
            "evidence": "readability tool / W3C COGA",
            "severity": "medium",
            "status": "pending",
        },
        {
            "id": "r2",
            "block_id": "p-2",
            "type": "difficult_word",
            "original": "their parents earn a limited income.",
            "suggestion": "their parents do not earn much money.",
            "rationale": "'limited income' is a harder phrase for early readers",
            "evidence": "readability tool / W3C COGA",
            "severity": "low",
            "status": "pending",
        },
    ]
}

_LAYOUT = {
    "recommendations": [
        {
            "id": "r3",
            "block_id": "p-1",
            "type": "line_spacing",
            "original": "line-height: 1.2",
            "suggestion": "line-height: 1.6",
            "rationale": "line spacing is 1.2; target >= 1.5",
            "evidence": "DOM metrics / WCAG 1.4.12",
            "severity": "medium",
            "status": "pending",
        },
    ]
}

_P1 = SAMPLE_BLOCKS[0]["text"]
_ADAPTED_UI = {
    "changes": [
        {
            "block_id": "p-1",
            "action": "replace_text",
            "value": _P1.replace(_TEXT["recommendations"][0]["original"], _TEXT["recommendations"][0]["suggestion"]),
        },
        {"block_id": "p-1", "action": "set_style", "value": "line-height: 1.6"},
    ]
}

MOCK_RESPONSES = {"text_recs": _TEXT, "layout_recs": _LAYOUT, "adapted_ui": _ADAPTED_UI}


def mock_response(task: str) -> str:
    """Return the fixed JSON text for a task, as a model would (a string)."""
    try:
        return json.dumps(MOCK_RESPONSES[task])
    except KeyError:
        raise KeyError(f"The mock has no response for task '{task}'. Known: {sorted(MOCK_RESPONSES)}") from None
