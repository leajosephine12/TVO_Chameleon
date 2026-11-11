"""
dyslexia_engine/app/guidelines/level2_plain_text.py
Level 2 guidelines: adapt the *language and structure* of the content.

Level 1 changes how text looks (CSS). Level 2 changes what the text says, so
these rules are applied by the AI model, not by a stylesheet.

SINGLE SOURCE OF TRUTH. Edit rules here and only here. The prompt in
model/prompt_instructions/level2_plain_text.py is built from this list.

Each rule's `params` has two control keys:
  handling: "rewrite"     -> sent to the model; the model returns a rewritten sentence/phrase
                             and apply_level2 swaps it in.
            "unsupported" -> kept as a guideline, but NOT sent to the model yet
                             (no safe way to apply it today).
  how:      one concrete instruction for the model: what to do and what NOT to touch.
            Required when handling is "rewrite".

The `source` field holds the reference codes from the research table (technique IDs
such as T9 or A6, or "Dys_spec" for the dyslexia specification).
"""
from ..schemas import Guideline

REWRITE = "rewrite"
UNSUPPORTED = "unsupported"

# ---- Tunable values ----------------------------------------------------------
SHORT_WORD_EXAMPLES = {
    "additional": "more",
    "approximately": "about",
    "assist": "help",
    "commence": "start",
    "demonstrate": "show",
    "purchase": "buy",
    "utilize": "use",
}
COMPLEX_PHRASE_EXAMPLES = {
    "a laissez-faire approach": "a hands-off approach",
    "a priori": "from the start",
    "status quo": "the way things are now",
    "per se": "in itself",
}
# Words with silent letters and simpler options (only swap when meaning is kept).
SILENT_LETTER_EXAMPLES = {
    "numb": "without feeling",
    "know": "understand",
    "knowledge": "what you understand",
    "listen": "pay attention",
}
DISRUPTIVE_PUNCTUATION = ["-", "\u2013", "\u2014"]   # hyphen, en dash, em dash
VAGUE_LINK_PHRASES = ["click here", "read more", "learn more", "more", "here", "link", "this page"]

LEVEL2_GUIDELINES: list[Guideline] = [
    # T9, T7 (better). Gap: unfamiliar terms without a definition.
    Guideline(id="L2.1.1", level=2, category="Plain English", title="Avoid complex jargon",
              rule="Use simple, familiar language instead of technical or unfamiliar terms.",
              params={"handling": REWRITE,
                      "how": "Swap technical or unfamiliar words for everyday ones. "
                             "If a term must stay, add a short plain definition in brackets after it.",
                      "replace_unfamiliar_terms": True, "define_term_if_it_must_stay": True},
              source="Scope. (2023, January 3). Writing dyslexic friendly content: Colours and fonts. Scope for Business. https://business.scope.org.uk/how-to-write-better-website-content-for-people-with-dyslexia/"),

    Guideline(id="L2.1.2", level=2, category="Plain English", title="Short words",
              rule='Prefer shorter words over longer alternatives (e.g., use "more" instead of "additional").',
              params={"handling": REWRITE,
                      "how": "Swap long words for short ones with the same meaning.",
                      "examples": SHORT_WORD_EXAMPLES},
              source="Scope. (2023, January 3). Writing dyslexic friendly content: Colours and fonts. Scope for Business. https://business.scope.org.uk/how-to-write-better-website-content-for-people-with-dyslexia/"),

    # Dys_spec. Gap: T6 defines how to detect passive voice but not how to change it to active.
    Guideline(id="L2.1.3", level=2, category="Plain English", title="Active voice",
              rule="Use active voice instead of passive voice wherever possible.",
              params={"handling": REWRITE,
                      "how": "Turn passive sentences into active ones. Keep the same facts. "
                             "If the actor is not named, leave the sentence as it is.",
                      "voice": "active",
                      "example": {"before": "The form was sent by the team.", "after": "The team sent the form."}},
              source="Scope. (2023, January 3). Writing dyslexic friendly content: Colours and fonts. Scope for Business. https://business.scope.org.uk/how-to-write-better-website-content-for-people-with-dyslexia/"),

    # T9, T7 (better)
    Guideline(id="L2.1.4", level=2, category="Plain English", title="Avoid complex phrases",
              rule='Avoid foreign expressions and complex phrases (e.g., "a laissez-faire approach").',
              params={"handling": REWRITE,
                      "how": "Replace foreign expressions and complex phrases with plain ones.",
                      "examples": COMPLEX_PHRASE_EXAMPLES},
              source="Scope. (2023, January 3). Writing dyslexic friendly content: Colours and fonts. Scope for Business. https://business.scope.org.uk/how-to-write-better-website-content-for-people-with-dyslexia/"),

    # Dys_spec. Gap: "unnecessary" cannot be defined by a fixed rule, so the AI model decides.
    Guideline(id="L2.1.5", level=2, category="Plain English", title="Avoid uppercase",
              rule="Avoid unnecessary use of uppercase letters.",
              params={"handling": REWRITE,
                      "how": "Change words in ALL CAPS to normal case. Keep capitals for sentence starts, "
                             "names, the word I, and acronyms most readers know.",
                      "decided_by": "ai",
                      "keep_uppercase": ["first letter of a sentence", "proper nouns", "the pronoun I",
                                         "acronyms the reader already knows"],
                      "convert_to_normal_case": ["words written in all capitals for emphasis", "all-caps headings"],
                      "use_bold_for_emphasis_instead": True},
              source="Scope. (2023, January 3). Writing dyslexic friendly content: Colours and fonts. Scope for Business. https://business.scope.org.uk/how-to-write-better-website-content-for-people-with-dyslexia/"),

    Guideline(id="L2.1.6", level=2, category="Plain English", title="Avoid silent letters",
              rule='Prefer words without silent letters where possible (e.g., avoid "numb").',
              params={"handling": REWRITE,
                      "how": "Low priority. Swap a word with a silent letter only when a simpler word "
                             "keeps the exact meaning. Skip it otherwise.",
                      "examples": SILENT_LETTER_EXAMPLES, "only_if_meaning_is_kept": True},
              source="Scope. (2023, January 3). Writing dyslexic friendly content: Colours and fonts. Scope for Business. https://business.scope.org.uk/how-to-write-better-website-content-for-people-with-dyslexia/"),

    Guideline(id="L2.1.7", level=2, category="Plain English", title="Avoid disruptive punctuation",
              rule="Use commas instead of hyphens or em-dashes within sentences to maintain reading flow.",
              params={"handling": REWRITE,
                      "how": "Replace dashes (en dash, em dash) used inside a sentence with commas. "
                             "Keep hyphens inside compound words and ranges.",
                      "replace": DISRUPTIVE_PUNCTUATION, "with": ",",
                      "keep_hyphen_in_compound_words": True},
              source="Scope. (2023, January 3). Writing dyslexic friendly content: Colours and fonts. Scope for Business. https://business.scope.org.uk/how-to-write-better-website-content-for-people-with-dyslexia/"),

    # Not applied yet: needs a "split paragraph" action in apply_level2.
    Guideline(id="L2.1.8", level=2, category="Plain English", title="One idea per paragraph",
              rule="Keep each paragraph focused on one main idea.",
              params={"handling": UNSUPPORTED,
                      "max_ideas_per_paragraph": 1, "split_paragraph_when_topic_changes": True},
              source="Scope. (2023, January 3). Writing dyslexic friendly content: Colours and fonts. Scope for Business. https://business.scope.org.uk/how-to-write-better-website-content-for-people-with-dyslexia/"),

    # Not applied yet: needs heading-level information and a heading-change action.
    Guideline(id="L2.1.9", level=2, category="Plain English", title="Logical heading structure",
              rule="Use relevant headings that follow a logical hierarchy (H1, H2, H3).",
              params={"handling": UNSUPPORTED,
                      "levels": ["h1", "h2", "h3"], "single_h1": True,
                      "no_skipped_levels": True, "headings_describe_the_section": True},
              source="Scope. (2023, January 3). Writing dyslexic friendly content: Colours and fonts. Scope for Business. https://business.scope.org.uk/how-to-write-better-website-content-for-people-with-dyslexia/"),

    # Not applied yet: needs link text and link targets in the input blocks.
    Guideline(id="L2.1.10", level=2, category="Plain English", title="Descriptive link text",
              rule='Use meaningful link descriptions instead of vague phrases such as "click here" or "read more".',
              params={"handling": UNSUPPORTED,
                      "vague_phrases": VAGUE_LINK_PHRASES, "link_text_describes_destination": True},
              source="Scope. (2023, January 3). Writing dyslexic friendly content: Colours and fonts. Scope for Business. https://business.scope.org.uk/how-to-write-better-website-content-for-people-with-dyslexia/"),
]


def get_guidelines(level: int) -> list[Guideline]:
    return [g for g in LEVEL2_GUIDELINES if g.level == level]


def get_rewrite_guidelines(enabled_ids: set[str] | None = None) -> list[Guideline]:
    """Rules the model should apply: handling == "rewrite", optionally limited to `enabled_ids`.

    enabled_ids=None means every rewrite rule. An id that does not exist, or that is not a
    rewrite rule, raises ValueError, so a typo fails loudly instead of silently dropping a rule.
    """
    rewrite = [g for g in LEVEL2_GUIDELINES if g.params.get("handling") == REWRITE]
    if enabled_ids is None:
        return rewrite
    valid = {g.id for g in rewrite}
    unknown = set(enabled_ids) - valid
    if unknown:
        raise ValueError(f"Not rewrite rules (unknown or unsupported): {sorted(unknown)}. Valid: {sorted(valid)}")
    return [g for g in rewrite if g.id in enabled_ids]