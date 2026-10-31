"""Safety checks on model output, plus helpers for handling untrusted page text.

Each `check_*` takes a list of Recommendation and returns a list of problem strings
(empty list = fine). The runner feeds these problems back to the model on a retry.

Limits (see README assumptions): these checks catch digits and names, not every possible meaning
change, and spelled-out numbers ("twenty-four") are not detected.
"""
import json
import re
from decimal import Decimal

from .schemas import Recommendation

_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_SENTENCE_START = re.compile(r"(?:^|[.!?]\s+)")


# ---------- untrusted page text ----------

def quote_as_data(data: object) -> str:
    """Render page text/findings as inert quoted data for the prompt.

    JSON-encoding escapes quotes and newlines, and '<' is escaped so page text can never
    contain a literal closing tag to break out of the <page_data> wrapper.
    """
    body = json.dumps(data, ensure_ascii=False, indent=1).replace("<", "\\u003c")
    return f"<page_data>\n{body}\n</page_data>"


# ---------- parsing ----------

def extract_json(text: str) -> object:
    """Parse the model's reply as JSON, tolerating ```json fences and chatter around the object."""
    cleaned = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if fenced:
        cleaned = fenced.group(1).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end > start:
            return json.loads(cleaned[start : end + 1])  # raises JSONDecodeError if still broken
        raise


# ---------- numbers ----------

def numbers_in(value: object) -> set[str]:
    """All numbers found anywhere in a string / dict / list, normalised ('1.20' == '1.2')."""
    if isinstance(value, bool):
        return set()
    if isinstance(value, (int, float)):
        value = str(value)
    if isinstance(value, str):
        return {format(Decimal(n).normalize(), "f") for n in _NUMBER.findall(value)}  # "f": 20 stays "20", not "2E+1"
    if isinstance(value, dict):
        return set().union(*(numbers_in(v) for v in value.values()), set())
    if isinstance(value, (list, tuple)):
        return set().union(*(numbers_in(v) for v in value), set())
    return set()


def check_rationale_numbers(recs: list[Recommendation], findings: object) -> list[str]:
    """Every number in a rationale must appear somewhere in the provided findings (the model copies, never computes)."""
    allowed = numbers_in(findings)
    problems = []
    for r in recs:
        unknown = sorted(numbers_in(r.rationale) - allowed)
        if unknown:
            problems.append(
                f"{r.id}: rationale uses number(s) {', '.join(unknown)} that are not in the provided findings. "
                "Copy numbers from the findings; never calculate or invent them."
            )
    return problems


# ---------- structure ----------

def check_unique_ids(recs: list[Recommendation]) -> list[str]:
    seen, problems = set(), []
    for r in recs:
        if r.id in seen:
            problems.append(f"Duplicate id '{r.id}'. Every recommendation needs a unique id.")
        seen.add(r.id)
    return problems


def check_status_pending(recs: list[Recommendation]) -> list[str]:
    return [f"{r.id}: status must be 'pending', got '{r.status}'." for r in recs if r.status != "pending"]


def check_known_blocks(recs: list[Recommendation], block_ids: set[str]) -> list[str]:
    return [
        f"{r.id}: block_id '{r.block_id}' is not one of the provided blocks ({', '.join(sorted(block_ids))})."
        for r in recs
        if r.block_id not in block_ids
    ]


def _squash(text: str) -> str:
    return " ".join(text.split())


def check_original_is_quoted(recs: list[Recommendation], block_text: dict[str, str]) -> list[str]:
    """`original` must be copied exactly from its block (whitespace aside), not paraphrased."""
    return [
        f"{r.id}: 'original' must be copied exactly from block {r.block_id}."
        for r in recs
        if r.block_id in block_text and _squash(r.original) not in _squash(block_text[r.block_id])
    ]


# ---------- meaning ----------

def _mid_sentence_capitals(text: str) -> set[str]:
    """Capitalised words that are not just the first word of a sentence (names, places)."""
    starts = {m.end() for m in _SENTENCE_START.finditer(text)}
    return {
        m.group()
        for m in re.finditer(r"[A-Z][a-zA-Z'-]*", text)
        if m.start() not in starts and not (m.start() > 0 and text[m.start() - 1].isalnum())
    }


def check_meaning_preserved(recs: list[Recommendation]) -> list[str]:
    """Cheap proxy for 'same facts': digits and names in the original must survive in the suggestion.

    A model can still change meaning in ways this cannot see; the prompt forbids it and the UI
    shows both texts so a person accepts or denies each change.
    """
    problems = []
    for r in recs:
        missing_nums = sorted(numbers_in(r.original) - numbers_in(r.suggestion))
        missing_names = sorted(w for w in _mid_sentence_capitals(r.original) if w not in r.suggestion)
        if missing_nums or missing_names:
            lost = ", ".join(missing_nums + missing_names)
            problems.append(f"{r.id}: suggestion lost facts from the original ({lost}). Keep every fact, number and name.")
    return problems
