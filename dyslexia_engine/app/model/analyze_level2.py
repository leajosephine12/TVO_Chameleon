"""
dyslexia_engine/app/levels/analyze_level2.py

>>> Replace with the real analyze_text when it exists (from stanin_analyze_text) <<<
Findings are flagged "STAND_IN": true. Every detector is a rough heuristic, on purpose: it points the
model at candidates, and the model decides whether a rewrite keeps the meaning.

what are kept:
- count_syllables
- split_sentences
- _words
- _difficult_words
- Constants: LONG_SENTENCE_WORDS, MAX_DIFFICULT_WORDS, DIFFICULT_MIN_SYLLABLES, TARGETS	Same values as before
- Regexes: _SENTENCE_BREAK, _WORD, and the _EASY_LONG_WORDS set	Same as before

functions are added:
- _find_terms	L2.1.2, L2.1.4, L2.1.6
- _is_passive	L2.1.3
- _all_caps_words	L2.1.5
- _dash_count

Always reported per block: word_count, reading_grade (Flesch-Kincaid), long_sentences, difficult_words.
Reported only when the rule is enabled (so the prompt stays short):
  L2.1.2 short_word_candidates   L2.1.3 passive_sentences   L2.1.4 complex_phrases
  L2.1.5 all_caps_words          L2.1.6 silent_letter_words L2.1.7 disruptive_punctuation
"""
import re

from ..guidelines.level2_plain_text import (
    COMPLEX_PHRASE_EXAMPLES,
    SHORT_WORD_EXAMPLES,
    SILENT_LETTER_EXAMPLES,
)

LONG_SENTENCE_WORDS = 20      # sentences with MORE words than this are reported
MAX_DIFFICULT_WORDS = 5       # per block
MAX_ITEMS = 5                 # cap for every other list, per block
DIFFICULT_MIN_SYLLABLES = 3
TARGETS = {"grade_level": "3-5", "max_sentence_words": "15-20"}
DETECTED_RULES = {"L2.1.1", "L2.1.2", "L2.1.3", "L2.1.4", "L2.1.5", "L2.1.6", "L2.1.7"}

_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(])")
_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'-]*")
_EASY_LONG_WORDS = {
    "different", "family", "every", "everyone", "everything", "another", "together", "beautiful",
    "important", "usually", "anything", "something", "remember", "yesterday", "tomorrow",
}

# L2.1.3: a form of "to be" + a past participle (-ed, or a common irregular one)
_PASSIVE = re.compile(r"\b(?:am|is|are|was|were|be|been|being)\s+(?:\w+ly\s+)?(\w+)\b", re.I)
_IRREGULAR_PARTICIPLES = {
    "given", "taken", "made", "done", "seen", "written", "sent", "built", "found", "held", "kept",
    "known", "shown", "told", "brought", "bought", "caught", "taught", "chosen", "broken", "driven",
}

# L2.1.5: all-caps words of 2+ letters, minus acronyms most readers know (the model keeps those anyway)
_ALL_CAPS = re.compile(r"\b[A-Z]{2,}\b")
_COMMON_ACRONYMS = {"USA", "UK", "US", "UN", "EU", "PDF", "HTML", "CSS", "FAQ", "TV", "DVD", "ID", "OK", "AM", "PM"}

# L2.1.7: en dash, em dash, "--", or a spaced hyphen. Hyphens inside words and number ranges are fine.
_DASH = re.compile(r"[\u2013\u2014]|--|(?<=\s)-(?=\s)")


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


def _find_terms(text: str, mapping: dict[str, str]) -> list[dict]:
    """Terms from a guideline word list that appear in the text, with the simpler option and a count."""
    lowered = text.lower()
    out = []
    for term, simpler in mapping.items():
        n = len(re.findall(rf"\b{re.escape(term)}\b", lowered))
        if n:
            out.append({"term": term, "simpler": simpler, "count": n})
    return out[:MAX_ITEMS]


def _is_passive(sentence: str) -> bool:
    for m in _PASSIVE.finditer(sentence):
        participle = m.group(1).lower()
        if participle in _IRREGULAR_PARTICIPLES:
            return True
        if participle.endswith("ed") and len(participle) > 4 and not participle.endswith("eed"):
            return True
    return False


def _all_caps_words(text: str) -> list[str]:
    seen: dict[str, None] = {}
    for w in _ALL_CAPS.findall(text):
        if w not in _COMMON_ACRONYMS:
            seen.setdefault(w)
    return list(seen)[:MAX_ITEMS]


def _dash_count(text: str) -> int:
    count = 0
    for m in _DASH.finditer(text):
        before, after = text[m.start() - 1:m.start()], text[m.end():m.end() + 1]
        if before.isdigit() and after.isdigit():  # a range such as 2010-2020
            continue
        count += 1
    return count


def _analyze_block(block: dict, active: set[str]) -> dict:
    text = block["text"]
    sentences = split_sentences(text)
    counts = [len(_words(s)) for s in sentences]
    words = sum(counts)
    syllables = sum(count_syllables(w) for s in sentences for w in _words(s))
    grade = round(0.39 * (words / len(sentences)) + 11.8 * (syllables / words) - 15.59, 1) if words else None
    result = {
        "block_id": block["block_id"],
        "word_count": words,
        "reading_grade": grade,
        "long_sentences": [
            {"text": s, "word_count": n} for s, n in zip(sentences, counts) if n > LONG_SENTENCE_WORDS
        ],
        "difficult_words": _difficult_words(sentences),
    }
    if "L2.1.2" in active:
        result["short_word_candidates"] = _find_terms(text, SHORT_WORD_EXAMPLES)
    if "L2.1.3" in active:
        passive = [s for s in sentences if _is_passive(s)]
        result["passive_sentence_count"] = len(passive)
        result["passive_sentences"] = passive[:MAX_ITEMS]
    if "L2.1.4" in active:
        result["complex_phrases"] = _find_terms(text, COMPLEX_PHRASE_EXAMPLES)
    if "L2.1.5" in active:
        result["all_caps_words"] = _all_caps_words(text)
    if "L2.1.6" in active:
        result["silent_letter_words"] = _find_terms(text, SILENT_LETTER_EXAMPLES)
    if "L2.1.7" in active:
        result["disruptive_punctuation_count"] = _dash_count(text)
    return result


def analyze_level2_plain_text(blocks: list[dict], enabled_rules: set[str] | None = None) -> dict:
    """blocks: [{"block_id", "text"}] -> findings in the shape generate_text_recommendations expects.

    enabled_rules: Level 2 rule ids, or None for all. Only the matching detectors run.
    """
    active = DETECTED_RULES if enabled_rules is None else DETECTED_RULES & set(enabled_rules)
    return {
        "STAND_IN": True,
        "targets": dict(TARGETS),
        "rules_checked": sorted(active),
        "blocks": [_analyze_block(b, active) for b in blocks],
    }