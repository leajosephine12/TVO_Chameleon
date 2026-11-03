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


def test_prompt_says_to_flag_only_measurements_outside_the_guideline_range():
    fake = FakeModel(reply(rec()))
    gen(fake)
    text = fake.calls[0][0]["content"]
    assert "outside the range" in text and "16px, is fine" in text and "Do not report a measurement that is inside its range" in text
    assert "only what you write in 'suggestion'" in text
    assert "16 to 19 pixels" in fake.calls[0][1]["content"][0]["text"]  # the ranges themselves are in the data


# ---- range guard: a measurement already inside the guideline range gets no suggestion ----

from app.model.layout_recs import drop_in_range, layout_ranges  # noqa: E402


def drop(recs, metrics):
    """drop_in_range on test dicts; returns the ids that were kept."""
    return [r.id for r in drop_in_range([Recommendation(**r) for r in recs], metrics)]


def metrics_for(**by_block):
    return {"blocks": [{"block_id": b, **m} for b, m in by_block.items()]}


def css_rec(rid, block, prop, value, original="x: 0", type="font_size"):
    return rec(id=rid, block_id=block, type=type, original=original, suggestion=f"{prop}: {value}", rationale="problem")


def test_ranges_are_read_from_the_guideline_sentences():
    assert layout_ranges() == {"min_font_size_px": 16.0, "min_line_height": 1.5, "max_line_length_chars": 70.0}


def test_unreadable_guideline_wording_fails_loudly(monkeypatch):
    from app.model import layout_recs
    changed = [g.model_copy(update={"rule": "Use a bigger font."}) if g.id == "L1.1.2" else g for g in layout_recs.LEVEL1_GUIDELINES]
    monkeypatch.setattr(layout_recs, "LEVEL1_GUIDELINES", changed)
    with pytest.raises(RuntimeError, match="min_font_size_px"):
        layout_ranges()


def test_a_16px_block_gets_no_font_size_suggestion():
    metrics = metrics_for(**{"p-1": {"font_size_px": 16}, "p-3": {"font_size_px": 14}})
    out = generate_layout_recommendations(
        TINY_PNG, metrics, caller=FakeModel(reply(
            css_rec("a", "p-1", "font-size", "18px", "font-size: 16px"),
            css_rec("b", "p-3", "font-size", "18px", "font-size: 14px"))))
    assert [(r.block_id, r.suggestion) for r in out] == [("p-3", "font-size: 18px")] and out[0].id == "r1"


def test_other_in_range_measurements_are_dropped_and_real_problems_kept():
    metrics = metrics_for(**{"p-1": {"line_height": 1.56, "line_length_chars": 70}, "p-2": {"line_height": 1.2, "line_length_chars": 129}})
    recs = [
        css_rec("a", "p-1", "line-height", "1.6", type="line_spacing"),   # 1.56 >= 1.5: fine
        css_rec("b", "p-2", "line-height", "1.6", type="line_spacing"),   # 1.2 < 1.5: real
        css_rec("c", "p-1", "max-width", "65ch", type="line_length"),     # 70 <= 70: fine
        css_rec("d", "p-2", "max-width", "65ch", type="line_length"),     # 129 > 70: real
    ]
    assert drop(recs, metrics) == ["b", "d"]


def test_boundaries_and_unknowns_are_kept():
    metrics = metrics_for(**{"p-1": {"font_size_px": 15.9}, "p-2": {}})
    recs = [css_rec("a", "p-1", "font-size", "18px"),                      # just under 16: real
            css_rec("b", "p-2", "font-size", "18px"),                      # no measurement: cannot judge, keep
            css_rec("c", "p-9", "font-size", "18px"),                      # block not measured: keep
            css_rec("d", "p-1", "font-size", "1.2em", type="heading_size"),  # heading: not judged
            rec(id="e", type="break_into_steps", suggestion="Break this into steps.")]  # not CSS: not judged
    assert drop(recs, metrics) == ["a", "b", "c", "d", "e"]


def test_page_wide_suggestion_is_dropped_only_if_every_block_is_in_range():
    page = css_rec("a", "page", "font-size", "18px")
    assert drop([page], metrics_for(**{"p-1": {"font_size_px": 16}, "p-2": {"font_size_px": 18}})) == []
    assert drop([page], metrics_for(**{"p-1": {"font_size_px": 16}, "p-2": {"font_size_px": 14}})) == ["a"]


def test_the_drop_is_logged(caplog):
    import logging
    caplog.set_level(logging.INFO, logger="app.model")
    drop([css_rec("a", "p-1", "font-size", "18px")], metrics_for(**{"p-1": {"font_size_px": 16}}))
    assert any("dropped a" in m.getMessage() and "inside the guideline range" in m.getMessage() for m in caplog.records)


def test_mock_mode_is_not_judged_against_the_input(monkeypatch):
    monkeypatch.setenv("MODEL_MOCK", "1")
    assert generate_layout_recommendations(TINY_PNG, metrics_for(**{"p-1": {"line_height": 2.0}}))  # mock rec still returned
