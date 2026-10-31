"""STAND-IN for the team's analyze_text tool. Plain code, no model, no network.

>>> Replace this with the real analyze_text when it exists. <<<
It exists so call 1 can be run end to end now. The output follows the findings shape proposed in
app/model/README.md, and is flagged "STAND_IN": true so nobody mistakes it for the real tool.

Rough heuristics, on purpose (see the README assumptions):
- sentences are split on . ! ? followed by a capital letter, so abbreviations like "e.g. Foo" can split wrongly
- syllables are estimated from vowel groups, so counts (and therefore the grade) can be off by a little;
  a number such as "40" counts as one word of one syllable
- "difficult" = 3+ syllables, longest first, minus a tiny list of easy long words. A real tool should use a word-frequency list
- reading_grade is the Flesch-Kincaid grade level: 0.39 * (words / sentences) + 11.8 * (syllables / words) - 15.59
"""
import re

LONG_SENTENCE_WORDS = 20      # sentences with MORE words than this are reported
MAX_DIFFICULT_WORDS = 5       # per block
DIFFICULT_MIN_SYLLABLES = 3
TARGETS = {"grade_level": "3-5", "max_sentence_words": "15-20"}  # same targets the README example uses

_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(])")
_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'-]*")
_EASY_LONG_WORDS = {
    "different", "family", "every", "everyone", "everything", "another", "together", "beautiful",
    "important", "usually", "anything", "something", "remember", "yesterday", "tomorrow",
}


def count_syllables(word: str) -> int:
    if word.isdigit():
        return 1
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 0
    count = len(re.findall(r"[aeiouy]+", w))
    if w.endswith("e") and not w.endswith(("le", "ee", "ye")) or (w.endswith("ed") and not w.endswith(("ted", "ded"))):
        count -= 1
    elif w.endswith("es") and not w.endswith(("ses", "xes", "zes", "ces", "ges", "ches", "shes")):
        count -= 1
    return max(count, 1)


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_BREAK.split(text.strip()) if s.strip()]


def _words(sentence: str) -> list[str]:
    return _WORD.findall(sentence)


def _difficult_words(sentences: list[str]) -> list[str]:
    found: dict[str, int] = {}  # word -> syllables, in order of first appearance
    for s in sentences:
        for i, w in enumerate(_words(s)):
            proper_noun = i > 0 and w[0].isupper()  # names and places are not "hard words"
            n = count_syllables(w)
            if proper_noun or n < DIFFICULT_MIN_SYLLABLES or w.lower() in _EASY_LONG_WORDS:
                continue
            found.setdefault(w.lower(), n)
    ranked = sorted(found, key=lambda w: (-found[w], -len(w)))  # stable: ties keep page order
    return ranked[:MAX_DIFFICULT_WORDS]


def _analyze_block(block: dict) -> dict:
    sentences = split_sentences(block["text"])
    counts = [len(_words(s)) for s in sentences]
    words = sum(counts)
    syllables = sum(count_syllables(w) for s in sentences for w in _words(s))
    grade = round(0.39 * (words / len(sentences)) + 11.8 * (syllables / words) - 15.59, 1) if words else None
    return {
        "block_id": block["block_id"],
        "word_count": words,
        "reading_grade": grade,
        "long_sentences": [
            {"text": s, "word_count": n} for s, n in zip(sentences, counts) if n > LONG_SENTENCE_WORDS
        ],
        "difficult_words": _difficult_words(sentences),
    }


def standin_analyze_text(blocks: list[dict]) -> dict:
    """blocks: [{"block_id", "text"}] -> findings in the shape generate_text_recommendations expects."""
    return {
        "STAND_IN": True,
        "targets": dict(TARGETS),
        "blocks": [_analyze_block(b) for b in blocks],
    }
