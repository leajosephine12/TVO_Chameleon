import base64
import json
from pathlib import Path

import pytest

from app import guidelines
from app.model.layout_recs import generate_layout_recommendations, layout_targets, screenshot_to_data_url
from app.model.mock import mock_response
from app.model.runner import ModelOutputError
from app.model.sample_data import FAKE_LAYOUT_METRICS, TINY_PNG
from app.model.schemas import Recommendation

SAMPLES = Path(__file__).resolve().parents[2] / "samples"


class FakeModel:
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def __call__(self, messages, **kwargs):
        self.calls.append([dict(m) for m in messages])
        return self.replies[min(len(self.calls), len(self.replies)) - 1]


def reply(*recs):
    return json.dumps({"recommendations": list(recs)})


def rec(**kw):
    return json.loads(mock_response("layout_recs"))["recommendations"][0] | kw


def gen(fake, **kw):
    return generate_layout_recommendations(TINY_PNG, FAKE_LAYOUT_METRICS, caller=fake, **kw)


@pytest.fixture(autouse=True)
def real_mode(monkeypatch):
    for k in ("MODEL_MOCK", "MODEL_MAX_RETRIES"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("MODEL_NAME", "fake-vision-model")


# ---- targets come from guidelines.py ----

def test_targets_are_imported_not_copied():
    t = layout_targets()["applied_by_adapter"]
    assert t["font_size_px"] == guidelines.BODY_FONT_PX and t["line_height"] == guidelines.LINE_HEIGHT
    assert t["max_line_length_chars"] == guidelines.MAX_LINE_CH
    assert t["smallest_heading_scale"] == min(guidelines.HEADING_SCALE.values())
    rules = layout_targets()["guideline_rules"]
    assert rules["L1.1.6"] == next(g.rule for g in guidelines.LEVEL1_GUIDELINES if g.id == "L1.1.6")


def test_targets_follow_a_change_in_guidelines(monkeypatch):
    monkeypatch.setattr("app.model.layout_recs.LINE_HEIGHT", 1.9)
    assert layout_targets()["applied_by_adapter"]["line_height"] == 1.9


# ---- mock mode ----

def test_mock_mode_returns_plain_list(monkeypatch):
    monkeypatch.setenv("MODEL_MOCK", "1")
    out = generate_layout_recommendations(TINY_PNG, FAKE_LAYOUT_METRICS)
    assert type(out) is list and all(isinstance(r, Recommendation) for r in out) and out[0].type == "line_spacing"


def test_mock_mode_works_for_any_page(monkeypatch):
    monkeypatch.setenv("MODEL_MOCK", "1")
    assert generate_layout_recommendations(TINY_PNG, {"blocks": [{"block_id": "div-3"}]})


# ---- real-mode path with a fake model ----

def test_good_reply_and_image_is_sent_in_openai_vision_format():
    fake = FakeModel(reply(rec()))
    out = gen(fake)
    assert type(out) is list and out[0].id == "r1"
    content = fake.calls[0][-1]["content"]
    assert content[0]["type"] == "text" and "<page_data>" in content[0]["text"]
    assert content[1]["type"] == "image_url" and content[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert "1.6" in content[0]["text"] and "at least 1.5" in content[0]["text"]  # targets are in the prompt


def test_invented_number_rejected_then_fixed():
    fake = FakeModel(reply(rec(rationale="line spacing is 1.1; target >= 1.5")), reply(rec()))
    gen(fake)
    assert "1.1" in fake.calls[1][-1]["content"] and "not in the provided findings" in fake.calls[1][-1]["content"]


def test_target_numbers_from_guidelines_are_allowed():
    ok = rec(rationale="font is 14 px; the guideline says 16 to 19 pixels", block_id="p-2", type="font_size")
    assert gen(FakeModel(reply(ok)))[0].block_id == "p-2"


def test_unknown_block_rejected_but_page_is_allowed():
    fake = FakeModel(reply(rec(block_id="p-77")), reply(rec(block_id="page")))
    assert gen(fake)[0].block_id == "page" and len(fake.calls) == 2


def test_gives_clear_error_after_retries():
    fake = FakeModel("sorry, I can't see images")
    with pytest.raises(ModelOutputError) as e:
        gen(fake)
    assert len(fake.calls) == 3 and e.value.task == "layout_recs"


# ---- input checks ----

def test_screenshot_formats():
    assert screenshot_to_data_url(TINY_PNG).startswith("data:image/png;base64,")
    assert screenshot_to_data_url(base64.b64encode(TINY_PNG).decode()).startswith("data:image/png;base64,")
    assert screenshot_to_data_url("data:image/png;base64," + base64.b64encode(TINY_PNG).decode())
    assert screenshot_to_data_url(b"\xff\xd8\xff\xe0" + b"0" * 10).startswith("data:image/jpeg")


@pytest.mark.parametrize("bad", [b"not an image", "%%% not base64 %%%", b""])
def test_bad_screenshot_is_a_clear_error(bad):
    with pytest.raises(ValueError, match="screenshot"):
        screenshot_to_data_url(bad)


def test_bad_metrics_is_a_clear_error():
    with pytest.raises(ValueError, match="blocks"):
        generate_layout_recommendations(TINY_PNG, {"blocks": []})


# ---- samples ----

def test_saved_layout_samples_match_the_mock(monkeypatch):
    monkeypatch.setenv("MODEL_MOCK", "1")
    saved_in = json.loads((SAMPLES / "layout_recs_input.json").read_text(encoding="utf-8"))
    saved_out = json.loads((SAMPLES / "layout_recs_output.json").read_text(encoding="utf-8"))
    fresh = generate_layout_recommendations(TINY_PNG, saved_in["metrics"], start_id=3)
    assert saved_out == [r.model_dump() for r in fresh]


def test_css_types_must_have_a_real_css_suggestion():
    bad = rec(type="font_size", original="font_size_px: 14", suggestion="font_size_px: 18", rationale="font is 14 px")
    fake = FakeModel(reply(bad), reply(rec()))
    gen(fake)
    assert "must be CSS" in fake.calls[1][-1]["content"] and "font_size_px" in fake.calls[1][-1]["content"]


def test_non_css_types_may_have_plain_english_suggestions():
    steps = rec(id="r8", type="break_into_steps", original="one dense paragraph", suggestion="Break this into numbered steps.", rationale="dense block")
    assert gen(FakeModel(reply(steps)))[0].type == "break_into_steps"


def test_prompt_shows_exact_css_formats():
    fake = FakeModel(reply(rec()))
    gen(fake)
    text = fake.calls[0][0]["content"]
    assert "line-height: 1.6" in text and "max-width: 65ch" in text and "once" in text


def test_ids_are_assigned_by_code_so_duplicates_from_the_model_do_not_matter():
    dup = [rec(id="r1"), rec(id="r1", type="font_size", original="font-size: 14px", suggestion="font-size: 18px", rationale="font is 14 px")]
    fake = FakeModel(reply(*dup))
    out = gen(fake, start_id=5)
    assert [r.id for r in out] == ["r5", "r6"] and len(fake.calls) == 1  # no retry spent on ids


def test_layout_recommendations_are_capped_too():
    recs = [rec(id=f"m{i}", severity=s) for i, s in enumerate(["low", "high", "low", "low", "medium", "low"])]
    out = gen(FakeModel(reply(*recs)))
    assert len(out) == 4 and "high" in [r.severity for r in out] and "medium" in [r.severity for r in out]
    assert len(gen(FakeModel(reply(*recs)), max_recommendations=2)) == 2
