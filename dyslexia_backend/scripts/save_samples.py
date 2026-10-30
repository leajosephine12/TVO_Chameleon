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

from app.model.sample_data import FAKE_FINDINGS, SAMPLE_BLOCKS  # noqa: E402
from app.model.text_recs import generate_text_recommendations  # noqa: E402

SAMPLES = ROOT / "samples"


def save(name: str, data: object) -> None:
    (SAMPLES / name).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("saved", SAMPLES / name)


if __name__ == "__main__":
    SAMPLES.mkdir(exist_ok=True)
    save("text_recs_input.json", {"blocks": SAMPLE_BLOCKS, "findings": FAKE_FINDINGS})
    save("text_recs_output.json", [r.model_dump() for r in generate_text_recommendations(SAMPLE_BLOCKS, FAKE_FINDINGS)])
