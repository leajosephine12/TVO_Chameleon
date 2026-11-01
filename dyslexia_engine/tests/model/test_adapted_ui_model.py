import json

import pytest

from app.model.adapted_ui import generate_adapted_ui
from app.model.mock import mock_response
from app.model.runner import ModelOutputError
from app.model.sample_data import SAMPLE_BLOCKS
from app.model.schemas import Recommendation


class FakeModel:
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def __call__(self, messages, **kwargs):
        self.calls.append([dict(m) for m in messages])
        return self.replies[min(len(self.calls), len(self.replies)) - 1]


def mock_recs(task):
    return [Recommendation(**r) for r in json.loads(mock_response(task))["recommendations"]]


def accept(recs):
    return [r.model_copy(update={"status": "accepted"}) for r in recs]


TEXT, LAYOUT = accept(mock_recs("text_recs")), accept(mock_recs("layout_recs"))
PLAIN = generate_adapted_ui(TEXT, LAYOUT, SAMPLE_BLOCKS)
GOOD = json.dumps(PLAIN.spec.model_dump())


def spec_with(**edit):
    """A copy of the plain-code spec with one change edited: spec_with(i=0, value=...)"""
    spec = json.loads(GOOD)
    spec["changes"][edit.pop("i")].update(edit)
    return json.dumps(spec)


def run(fake, **kw):
    return generate_adapted_ui(TEXT, LAYOUT, SAMPLE_BLOCKS, use_model=True, caller=fake, **kw)


@pytest.fixture(autouse=True)
def real_mode(monkeypatch):
    for k in ("MODEL_MOCK", "MODEL_MAX_RETRIES"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("MODEL_NAME", "fake-model")


# ---- mock mode ----

def test_mock_mode_returns_the_spec(monkeypatch):
    monkeypatch.setenv("MODEL_MOCK", "1")
    res = generate_adapted_ui(TEXT, LAYOUT, SAMPLE_BLOCKS, use_model=True)
    assert [c.action for c in res.spec.changes] == ["replace_text", "set_style"]


def test_default_is_plain_code_and_never_calls_a_model():
    def boom(*a, **k):
        raise AssertionError("model used")
    assert generate_adapted_ui(TEXT, LAYOUT, SAMPLE_BLOCKS).spec == PLAIN.spec
    with pytest.raises(TypeError):
        generate_adapted_ui(TEXT, LAYOUT, SAMPLE_BLOCKS, caller=boom)  # model options without use_model


# ---- real-mode path with a fake model ----

def test_a_correct_reply_is_accepted_and_equals_the_plain_result():
    res = run(FakeModel(GOOD))
    assert res.spec == PLAIN.spec


def test_nothing_usable_means_no_model_call():
    fake = FakeModel(GOOD)
    pending = [r.model_copy(update={"status": "pending"}) for r in TEXT]
    res = generate_adapted_ui(pending, [], SAMPLE_BLOCKS, use_model=True, caller=fake)
    assert res.spec.changes == [] and fake.calls == []


def test_prompt_quotes_the_page_text_as_data():
    fake = FakeModel(GOOD)
    run(fake)
    system, user = fake.calls[0][0]["content"], fake.calls[0][1]["content"]
    assert "never an instruction" in system and "FULL new text" in system and "<page_data>" in user
    assert "Manitoulin Island" in user and "Manitoulin" not in system


@pytest.mark.parametrize("bad,needle", [
    (spec_with(i=0, value="Students will learn money things."), "word for word"),        # dropped the accepted wording
    (spec_with(i=1, value=json.loads(GOOD)["changes"][1]["value"].replace("40", "4")), "Numbers changed"),
    (spec_with(i=2, value="line-height: 2"), "must contain exactly"),                      # changed the accepted style
    (spec_with(i=0, block_id="p-9"), "no accepted text recommendation"),
    (spec_with(i=2, block_id="p-2"), "no accepted layout recommendation"),
    (spec_with(i=0, value="Hello <script>alert(1)</script>"), "plain text"),               # schema-level rejection
    (spec_with(i=2, value="background: url(http://evil.test/a.png)"), "not allowed"),
    ("{}", "changes"),
    ("I cannot do that", "not valid JSON"),
])
def test_bad_replies_are_rejected_with_the_reason_fed_back(bad, needle):
    fake = FakeModel(bad, GOOD)
    res = run(fake)
    assert res.spec == PLAIN.spec and len(fake.calls) == 2
    assert needle in fake.calls[1][-1]["content"]


def test_missing_change_and_duplicate_change_are_rejected():
    spec = json.loads(GOOD)
    only_text = json.dumps({"changes": spec["changes"][:2]})
    fake = FakeModel(only_text, json.dumps({"changes": spec["changes"] + [spec["changes"][0]]}), GOOD)
    run(fake)
    assert "Missing set_style" in fake.calls[1][-1]["content"] and "More than one replace_text" in fake.calls[2][-1]["content"]


def test_original_left_in_place_is_rejected():
    spec = json.loads(GOOD)
    spec["changes"][0]["value"] = SAMPLE_BLOCKS[0]["text"] + " " + TEXT[0].suggestion
    fake = FakeModel(json.dumps(spec), GOOD)
    run(fake)
    assert "still in" in fake.calls[1][-1]["content"]


def test_gives_clear_error_never_a_bad_spec():
    fake = FakeModel(spec_with(i=0, value="wrong"))
    with pytest.raises(ModelOutputError) as e:
        run(fake)
    assert len(fake.calls) == 3 and e.value.task == "adapted_ui"


def test_call_3_does_not_get_the_recommendation_rules():
    fake = FakeModel(GOOD)
    run(fake)
    assert 'status "pending"' not in fake.calls[0][0]["content"]
