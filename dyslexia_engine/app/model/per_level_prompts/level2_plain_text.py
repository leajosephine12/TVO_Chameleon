"""
dyslexia_engine/app/model/prompt_instructions/level2_plain_text.py

Builds the Level 2 prompt text from guidelines/level2_plain_text.py.
This file holds NO rule wording. To change a rule, edit the guideline (its `how`,
`handling`, or examples) and the prompt follows.
"""
from ...guidelines.level2_plain_text import get_rewrite_guidelines


def _render_params(params: dict) -> str:
    """Optional extras from a guideline: word examples and a before/after example."""
    parts = []
    examples = params.get("examples")
    if isinstance(examples, dict) and examples:
        parts.append("Examples: " + "; ".join(f'"{a}" -> "{b}"' for a, b in examples.items()) + ".")
    example = params.get("example")
    if isinstance(example, dict) and example.get("before") and example.get("after"):
        parts.append(f'Example: "{example["before"]}" -> "{example["after"]}".')
    return " ".join(parts)


def _rule_lines(enabled_ids: set[str] | None) -> list[str]:
    lines = []
    for g in get_rewrite_guidelines(enabled_ids):
        how = g.params.get("how")
        if not how:
            raise ValueError(f"Guideline {g.id} has handling 'rewrite' but no 'how' text.")
        extra = _render_params(g.params)
        lines.append(f"- {g.id} {g.title}: {how}" + (f" {extra}" if extra else ""))
    return lines

# Prompts are based on written INSTRUCTIONS
def build_level2_instructions(enabled_ids: set[str] | None = None) -> str:
    """The Level 2 prompt. enabled_ids=None means every rewrite rule."""
    lines = _rule_lines(enabled_ids)
    if not lines:
        raise ValueError("No Level 2 rewrite rules are enabled, so there is nothing to put in the prompt.")
    rules = "\n".join(lines)
    return f"""\
You help make web page text easier to read for students with dyslexia and reading difficulties (target: Grade 3-5).
You are given text blocks and findings from a readability tool: long sentences, reading levels and difficult words.

Plain-language rules (apply only the ones that fit the text):
{rules}

How to apply them:
- Write ONE recommendation per affected sentence or phrase. If several rules apply to it, combine them in one rewrite. Never write two recommendations for the same text.
- Never change facts, numbers, names, quotes, code, or the meaning. If a rewrite would change the meaning, skip it.
- Prefer the smallest change that fixes the problem.

Field guide:
- id: "r1", "r2", ... (the system renumbers them).
- block_id: the block the text came from.
- type: "long_sentence", "difficult_word", "reading_level" or "plain_language".
- original: the affected text, copied exactly from the block. Never empty.
- suggestion: your simpler version with the same facts, numbers and names.
- rationale: one short sentence saying why. If you mention a number, copy it from the findings exactly, for example "24 words; Grade 3-5 target <= 15-20".
- evidence: the rule ids you applied, for example "L2.1.2, L2.1.3 / Dys_spec".
- severity: "high" for a problem far beyond the target, "medium" for a clear problem, "low" for a small one.
- status: "pending".
Only write recommendations for problems you can point to in the text. If there are none, return {{"recommendations": []}}.

Keep the reply short, because a long reply is slow:
- 'rationale' is at most 15 words.
- Write compact JSON: no indentation and no blank lines."""