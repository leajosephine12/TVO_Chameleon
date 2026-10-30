import json

import pytest

from app.model.mock import mock_response
from app.model.sample_data import FAKE_FINDINGS, SAMPLE_BLOCKS
from app.model.standin_analyze_text import count_syllables, split_sentences, standin_analyze_text
from app.model.text_recs import generate_text_recommendations

P1, P2 = standin_analyze_text(SAMPLE_BLOCKS)["blocks"]


@pytest.mark.parametrize("word,n", [
    ("the", 1), ("income", 2), ("reasons", 2), ("students", 2), ("limited", 3), ("balanced", 2),
    ("consumers", 3), ("financial", 3), ("grocery", 3), ("community", 4), ("technology", 4), ("compound", 2),
])
def test_syllable_estimates(word, n):
    assert count_syllables(word) == n


def test_it_is_clearly_marked_as_a_stand_in():
    out = standin_analyze_text(SAMPLE_BLOCKS)
    assert out["STAND_IN"] is True


def test_output_matches_the_readme_findings_shape():
    out = standin_analyze_text(SAMPLE_BLOCKS)
    assert set(out) == {"STAND_IN", "targets", "blocks"} and set(out["targets"]) == {"grade_level", "max_sentence_words"}
    for b in out["blocks"]:
        assert set(b) == {"block_id", "word_count", "reading_grade", "long_sentences", "difficult_words"}
        assert all(set(ls) == {"text", "word_count"} for ls in b["long_sentences"])
    json.dumps(out)  # plain JSON types only


def test_sentence_split_on_the_tvo_paragraphs():
    assert [len(s.split()) for s in split_sentences(SAMPLE_BLOCKS[0]["text"])] == [18, 24, 24]
    assert [len(s.split()) for s in split_sentences(SAMPLE_BLOCKS[1]["text"])] == [17, 11, 18, 18]


def test_p1_counts_and_long_sentences():
    assert P1["block_id"] == "p-1" and P1["word_count"] == 66
    assert [ls["word_count"] for ls in P1["long_sentences"]] == [24, 24]
    assert P1["long_sentences"][0]["text"].startswith("Students compare different ways")


def test_p2_has_no_long_sentences():
    assert P2["word_count"] == 64 and P2["long_sentences"] == []


def test_long_sentences_agree_with_the_fake_findings():
    """The hand-written fake findings claimed these same two sentences; the stand-in finds them by itself."""
    fake = FAKE_FINDINGS["blocks"][0]["long_sentences"]
    assert P1["long_sentences"] == fake


def test_reading_grade_formula():
    one = standin_analyze_text([{"block_id": "p-1", "text": "The cat sat on the mat."}])["blocks"][0]
    assert one["reading_grade"] == pytest.approx(0.39 * 6 + 11.8 * 1 - 15.59, abs=0.06)
    assert P1["reading_grade"] > P2["reading_grade"] > 0  # the dense policy text reads harder than the story


def test_difficult_words_are_short_unique_and_skip_names():
    assert 0 < len(P1["difficult_words"]) <= 5 and "technology" in P1["difficult_words"]
    assert len(set(P1["difficult_words"])) == len(P1["difficult_words"])
    assert "manitoulin" not in P2["difficult_words"] and "community" in P2["difficult_words"]


def test_empty_text_does_not_crash():
    b = standin_analyze_text([{"block_id": "p-1", "text": "   "}])["blocks"][0]
    assert b["word_count"] == 0 and b["reading_grade"] is None and b["long_sentences"] == []


def test_feeds_call_1_end_to_end_and_passes_the_number_check(monkeypatch):
    """Stand-in findings -> call 1 with a fake model whose rationale quotes the stand-in's numbers."""
    monkeypatch.delenv("MODEL_MOCK", raising=False)
    monkeypatch.setenv("MODEL_NAME", "fake")
    findings = standin_analyze_text(SAMPLE_BLOCKS)
    rec = json.loads(mock_response("text_recs"))["recommendations"][0]  # rationale: "24 words; Grade 3-5 target <= 15-20"
    out = generate_text_recommendations(SAMPLE_BLOCKS, findings, caller=lambda *a, **k: json.dumps({"recommendations": [rec]}))
    assert out[0].rationale.startswith("24 words")
