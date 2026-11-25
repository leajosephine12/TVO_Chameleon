from types import SimpleNamespace

from app.levels.level2_plain_text import apply_level2


def rec(rid, block_id, original, suggestion):
    # apply_level2 only reads these four fields
    return SimpleNamespace(id=rid, block_id=block_id, original=original, suggestion=suggestion)


def run(text, original, suggestion):
    blocks = [{"block_id": "p-1", "text": text}]
    result = apply_level2(blocks, [rec("r1", "p-1", original, suggestion)])
    return result, result.blocks[0].text


def test_does_not_match_inside_longer_word():
    result, text = run("She was uninterested.", "interest", "curiosity")
    assert result.applied == []
    assert result.skipped[0].reason == "original text not found"
    assert text == "She was uninterested."


def test_matches_whole_word():
    result, text = run("A high interest rate.", "interest", "borrowing")
    assert result.applied == ["r1"]
    assert text == "A high borrowing rate."


def test_whitespace_tolerant():
    result, text = run("We left in  order\nto win.", "in order to", "to")
    assert result.applied == ["r1"]
    assert text == "We left to win."


def test_original_ending_in_punctuation():
    result, text = run("It is big. Really.", "It is big.", "It is large.")
    assert result.applied == ["r1"]
    assert text == "It is large. Really."


def test_ambiguous_is_skipped():
    result, _ = run("Plants need light. Plants need water.", "Plants", "They")
    assert result.applied == []
    assert result.skipped[0].reason == "original text ambiguous"


def test_backslash_in_suggestion_is_literal():
    result, text = run("Use the tool.", "tool", r"\1 tool")
    assert result.applied == ["r1"]
    assert text == r"Use the \1 tool."