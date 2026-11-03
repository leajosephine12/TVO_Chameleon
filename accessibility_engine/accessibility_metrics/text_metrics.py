"""analyze_text: T1-T7 + S1 over prose blocks (textstat + regex heuristics, no browser).

Input:  blocks [{"block_id", "text", "kind"?}] — T-metrics run on prose kinds only
        (p, blockquote; blocks without "kind" are treated as prose).
Output: {"findings": [...]} in the shared schema (see thresholds.finding).

Replaces dyslexia_engine's standin_analyze_text. Heuristics are deliberate
(sentence split, passive regex, proper-noun guess); THRESHOLDS holds the numbers.
"""
import re

import textstat

from .thresholds import THRESHOLDS, finding

PROSE_KINDS = {"p", "blockquote"}
MIN_WORDS_FOR_FORMULAS = 20  # readability formulas are noise on tiny blocks

_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(])")
_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'-]*")  # digits count as words ("40 minutes" = 2)
_CONJUNCTIONS = {
    "and", "but", "or", "nor", "yet", "so", "because", "although", "though",
    "while", "since", "unless", "whereas", "if", "when", "after", "before", "until",
}
# be-verb + past participle; -ed plus common irregulars. Heuristic on purpose (T6 is report-only).
_PASSIVE = re.compile(
    r"\b(am|is|are|was|were|be|been|being)\s+(\w+ed|known|given|taken|made|done|seen|found|"
    r"shown|written|held|kept|left|lost|told|brought|thought|built|sent|spent|set|put|chosen|driven)\b",
    re.I,
)


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_BREAK.split(text.strip()) if s.strip()]


def _proper_nouns(sentences: list[str]) -> set[str]:
    """Capitalised mid-sentence tokens (the PDF's proper-noun heuristic for T7)."""
    names: set[str] = set()
    for s in sentences:
        for w in _WORD.findall(s)[1:]:  # skip the sentence-initial word
            if w[0].isupper():
                names.add(w.lower())
    return names


def _rare_words(text: str, sentences: list[str]) -> tuple[list[str], float]:
    words = _WORD.findall(text)
    if not words:
        return [], 0.0
    proper = _proper_nouns(sentences)
    difficult = {w.lower() for w in textstat.difficult_words_list(text)} - proper
    rare = sorted({w.lower() for w in words if w.lower() in difficult})
    pct = round(100 * sum(1 for w in words if w.lower() in difficult) / len(words), 1)
    return rare, pct


def analyze_text(blocks: list[dict]) -> dict:
    findings: list[dict] = []
    for b in blocks:
        if b.get("kind", "p") not in PROSE_KINDS:
            continue
        text, bid = b["text"].strip(), b["block_id"]
        if not text:
            continue
        sentences = split_sentences(text)
        words = _WORD.findall(text)

        # T3 sentence length
        for s in sentences:
            n = len(_WORD.findall(s))
            if n > THRESHOLDS["T3"]["max_words"]:
                findings.append(finding("T3", bid, {"word_count": n, "sentence": s[:120]},
                                        f"Sentence has {n} words."))

        # T4 conjunctions per sentence
        for s in sentences:
            n = sum(1 for w in _WORD.findall(s) if w.lower() in _CONJUNCTIONS)
            if n > THRESHOLDS["T4"]["max_conjunctions"]:
                findings.append(finding("T4", bid, {"conjunctions": n, "sentence": s[:120]},
                                        f"Sentence chains {n} conjunctions."))

        # T6 passive voice (report-only)
        passives = [s[:120] for s in sentences if _PASSIVE.search(s)]
        if passives:
            findings.append(finding("T6", bid, {"passive_sentences": len(passives), "examples": passives[:3]},
                                    f"{len(passives)} sentence(s) in passive voice."))

        # S1 paragraph length
        if len(words) > THRESHOLDS["S1"]["max_words"] or len(sentences) > THRESHOLDS["S1"]["max_sentences"]:
            findings.append(finding("S1", bid, {"word_count": len(words), "sentence_count": len(sentences)},
                                    f"Paragraph has {len(words)} words in {len(sentences)} sentences."))

        if len(words) >= MIN_WORDS_FOR_FORMULAS:
            # T1 Flesch-Kincaid (reported with T2 as a range)
            fk = round(textstat.flesch_kincaid_grade(text), 1)
            dc = round(textstat.dale_chall_readability_score(text), 1)
            if fk > THRESHOLDS["T1"]["max_grade"]:
                findings.append(finding("T1", bid, {"flesch_kincaid_grade": fk, "dale_chall": dc},
                                        f"Reads at Grade {fk}."))
            # T2 Dale-Chall
            if dc > THRESHOLDS["T2"]["max_score"]:
                findings.append(finding("T2", bid, {"dale_chall": dc},
                                        f"Dale-Chall score {dc}."))
            # T7 rare words
            rare, pct = _rare_words(text, sentences)
            if pct > THRESHOLDS["T7"]["max_rare_pct"]:
                findings.append(finding("T7", bid, {"rare_words": rare[:10], "rare_pct": pct},
                                        "Low-frequency vocabulary."))

    return {"findings": findings}
