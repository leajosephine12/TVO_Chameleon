"""Save example inputs and outputs to samples/ for the demo fallback.

Run from dyslexia_backend/:   python scripts/save_samples.py
Uses the mock (MODEL_MOCK is forced on), so it needs no model. The saved outputs are what the
mock returns for the FAKE sample findings.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["MODEL_MOCK"] = "1"

from app.model.adapted_ui import generate_adapted_ui  # noqa: E402
from app.model.layout_recs import generate_layout_recommendations  # noqa: E402
from app.model.sample_data import FAKE_FINDINGS, FAKE_LAYOUT_METRICS, SAMPLE_BLOCKS, TINY_PNG  # noqa: E402
from app.model.text_recs import generate_text_recommendations  # noqa: E402

SAMPLES = ROOT / "samples"


def save(name: str, data: object) -> None:
    (SAMPLES / name).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("saved", SAMPLES / name)


if __name__ == "__main__":
    SAMPLES.mkdir(exist_ok=True)
    save("text_recs_input.json", {"blocks": SAMPLE_BLOCKS, "findings": FAKE_FINDINGS})
    save("text_recs_output.json", [r.model_dump() for r in generate_text_recommendations(SAMPLE_BLOCKS, FAKE_FINDINGS)])
    save("layout_recs_input.json", {"screenshot": "(omitted: a tiny placeholder image is used)", "metrics": FAKE_LAYOUT_METRICS})
    save("layout_recs_output.json", [r.model_dump() for r in generate_layout_recommendations(TINY_PNG, FAKE_LAYOUT_METRICS)])

    # call 3 is plain code: the user accepts the mock recommendations, the code builds the spec
    text = [r.model_copy(update={"status": "accepted"}) for r in generate_text_recommendations(SAMPLE_BLOCKS, FAKE_FINDINGS)]
    layout = [r.model_copy(update={"status": "accepted"}) for r in generate_layout_recommendations(TINY_PNG, FAKE_LAYOUT_METRICS)]
    save("adapted_ui_input.json", {
        "blocks": SAMPLE_BLOCKS,
        "accepted_text_recommendations": [r.model_dump() for r in text],
        "accepted_layout_recommendations": [r.model_dump() for r in layout],
    })
    save("adapted_ui_output.json", generate_adapted_ui(text, layout, SAMPLE_BLOCKS).spec.model_dump())
