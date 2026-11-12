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


def test_adapted_applies_typed_link_action():
    html = '<p>Choose a lesson.</p><a href="/lesson" class="cta">click here</a>'
    rec = {
        "id": "r10", "block_id": "a-1", "type": "J5", "original": "click here",
        "suggestion": "Choose a lesson", "rationale": "The link needs a clear purpose.",
        "evidence": "structure check / J5", "severity": "medium", "status": "accepted",
    }
    response = client.post("/adapted", json={"html": html, "recommendations": [rec]})
    out = response.json()
    assert response.status_code == 200 and "r10" in out["applied"] and "r10" not in out["skipped"]
    assert 'href="/lesson"' in out["adapted_html"] and ">Choose a lesson</a>" in out["adapted_html"]


def test_adapted_reports_renderer_rejection_as_skipped():
    rec = {
        "id": "r11", "block_id": "p-1", "type": "J5", "original": "Not a link",
        "suggestion": "Read the guide", "rationale": "The link needs a clear purpose.",
        "evidence": "structure check / J5", "severity": "medium", "status": "accepted",
    }
    response = client.post("/adapted", json={"html": "<p>Not a link</p>", "recommendations": [rec]})
    out = response.json()
    assert response.status_code == 200 and "r11" in out["skipped"] and "r11" not in out["applied"]


# ---- /adapted on realistic pages: links survive, input buttons work, one bad change never costs the rest ----

PAGE = (
    '<html><body><p>Students compare ways to save money. See <a href="/x">the guide</a>, then <b>try it</b>.</p>'
    '<input type="submit" value="OK">'
    "<section><p>Interest is the cost of borrowing money over time.</p></section></body></html>"
)
SECTION_TEXT = "Interest is the cost of borrowing money over time."


def model_rec(id, block, type, original, suggestion):
    # evidence that does not start with "Level <n> guideline" routes it to the model path, like a real model rec
    return dict(id=id, block_id=block, type=type, original=original, suggestion=suggestion, rationale="r",
                evidence="readability tool", severity="medium", status="accepted")


def adapt(recs, html=PAGE):
    r = client.post("/adapted", json={"html": html, "recommendations": recs})
    assert r.status_code == 200, r.text
    return r.json()


def test_a_text_edit_keeps_the_links_and_bold_and_adds_no_stray_spaces():
    out = adapt([model_rec("r1", "p-1", "long_sentence", "Students compare ways to save money.", "Students look at ways to save money.")])
    assert out["applied"] == ["r1"] and out["skipped"] == []
    html = out["adapted_html"]
    assert '<a href="/x">the guide</a>, then <b>try it</b>.' in html and "Students look at ways" in html
    assert "guide </a>" not in html and "guide ," not in html and "it ." not in html


def test_a_vague_input_button_label_is_fixed_using_its_value():
    out = adapt([model_rec("r1", "input-1", "J14", "OK", "Submit answers")])
    assert out["applied"] == ["r1"] and 'value="Submit answers"' in out["adapted_html"]


def test_a_too_long_heading_is_skipped_and_the_other_accepted_edit_still_applies():
    long_heading = "What interest means for people who borrow money from a bank"
    out = adapt([
        model_rec("r1", "p-1", "long_sentence", "Students compare ways to save money.", "Students look at ways to save money."),
        model_rec("r2", "section-1", "S3", SECTION_TEXT, long_heading),
    ])
    assert out["applied"] == ["r1"] and out["skipped"] == ["r2"]
    assert "Students look at ways" in out["adapted_html"] and long_heading not in out["adapted_html"]


def test_a_button_fix_with_no_original_is_reported_not_a_server_error():
    out = adapt([model_rec("r1", "input-1", "J14", "", "Submit answers")])
    assert out["applied"] == [] and out["skipped"] == ["r1"]


def test_general_accessibility_has_its_own_endpoints_and_rules_only_keeps_the_model_out_of_analyze():
    html = "<html><body><p>" + " ".join(["The plant grows in the sun, and it needs water every day"] * 3) + ".</p></body></html>"
    general = client.post("/analyze_general", json={"html": html}).json()
    recs = general["recommendations"]
    assert recs and all(r["change"] and (r["preview_html"] or r["preview_css"]) and r["title"] for r in recs)

    for r in recs:
        r["status"] = "accepted"
    out = client.post("/adapted_general", json={"html": html, "recommendations": recs}).json()
    assert out["applied"] == [r["id"] for r in recs] and out["adapted_html"] != html

    rules = client.post("/analyze", json={"html": HTML, "rules_only": True}).json()["recommendations"]
    assert rules and all(r["evidence"].startswith("Level 1 guideline") for r in rules)


def test_layout_fixes_are_computed_in_code_and_ship_even_when_the_model_step_fails(monkeypatch):
    """Text size, line spacing and line length need no model: one card per block, applied as one style change."""
    import genui.service as service
    from app.model.client import ModelCallError
    from genui import analyze_general, apply_general

    def no_model(*args, **kwargs):
        raise ModelCallError("model is down")

    monkeypatch.setattr(service, "plan_changes", no_model)
    html = "<html><body><p>Small and cramped text.</p><p>Fine text.</p></body></html>"
    measured = lambda metric, m, detail: {"metric_id": metric, "block_id": "p-1", "measured": m, "detail": detail,  # noqa: E731
                                          "threshold": "t", "source": "s", "tier": "C"}
    rendered = {"findings": [measured("L3", {"font_size_px": 12.0}, "Body text is 12px."),
                             measured("L2", {"line_height": 1.2, "text_align": "justify"}, "Line height 1.2, justified text")]}
    out = analyze_general(html, None, rendered)
    assert out["model_error"] == "model is down"
    [rec] = out["recommendations"]
    assert rec.type == "L2+L3" and rec.preview_css == "line-height: 1.5; text-align: left; font-size: 16px"

    rec.status = "accepted"
    applied = apply_general(html, [rec])
    assert applied["applied"] == [rec.id] and "font-size: 16px" in applied["adapted_html"]


def test_general_analysis_still_runs_when_the_page_cannot_be_rendered():
    html = "<html><body><p>Short text.</p></body></html>"
    r = client.post("/analyze_general", json={"html": html, "url": "http://127.0.0.1:9/nothing-here", "render": True})
    assert r.status_code == 200 and r.json()["layout_error"]
