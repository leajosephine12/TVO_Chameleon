"""Smallest end-to-end check: analyze then adapt the sample page, mock model.

Run: MODEL_MOCK=1 uv run pytest
"""
import os
from pathlib import Path

os.environ["MODEL_MOCK"] = "1"

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)
HTML = (Path(__file__).parents[1] / "dyslexia_engine/demo/sample_iframe.html").read_text()


def test_analyze_then_adapt():
    r = client.post("/analyze", json={"html": HTML})
    assert r.status_code == 200
    data = r.json()
    recs = data["recommendations"]
    assert data["model_error"] is None
    assert any(x["type"] == "typography" for x in recs)  # engine ran
    assert all(x["status"] == "pending" for x in recs)

    for x in recs:
        x["status"] = "accepted"
    r2 = client.post("/adapted", json={"html": HTML, "recommendations": recs})
    assert r2.status_code == 200
    out = r2.json()
    assert out["applied"]
    assert out["injected_css"]
    assert out["adapted_html"] != HTML


def test_adapted_applies_model_layout_rec():
    """An accepted call-2 layout rec must land as inline CSS — even when its type
    collides with an engine type name (recs are split by evidence, not type)."""
    rec = {
        "id": "r9", "block_id": "p-1", "type": "typography",
        "original": "", "suggestion": "line-height: 1.8",
        "rationale": "Line spacing below 1.5.", "evidence": "model judgement / L5",
        "severity": "medium", "status": "accepted",
    }
    r = client.post("/adapted", json={"html": HTML, "recommendations": [rec]})
    assert r.status_code == 200
    out = r.json()
    assert "r9" in out["applied"]
    assert "r9" not in out["skipped"]
    assert "line-height: 1.8" in out["adapted_html"]
