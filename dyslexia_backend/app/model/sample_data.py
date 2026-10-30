"""Sample inputs for tests, the smoke test and demos.

SAMPLE_BLOCKS are real paragraphs from a TVO Learn page.
FAKE_FINDINGS and FAKE_LAYOUT_METRICS are MADE UP (flagged FAKE_SAMPLE_DATA), shaped like what
analyze_text / layout_metrics might return. The real tool output shape has not been agreed yet,
so treat these shapes as an assumption. The numbers agree with the mock replies in mock.py.
"""

SAMPLE_BLOCKS = [
    {
        "block_id": "p-1",
        "text": (
            "Students will learn to create a plan to reach financial goals and identify ways to maintain "
            "balanced budgets. Students compare different ways that consumers can get value for their money "
            "when spending, such as using reward programs or taking advantage of sales. Students investigate "
            "the concepts of simple and compound interest using technology, (for example, a spreadsheet "
            "program) and explain how interest affects long-term financial planning."
        ),
    },
    {
        "block_id": "p-2",
        "text": (
            "Student One and their family live in a small community on the western edge of Manitoulin Island. "
            "The nearest grocery store is 40 minutes away from their home. Student One and their family can "
            "only afford to buy groceries once every two weeks for two reasons. First, the grocery store is "
            "far away from their home and second, their parents earn a limited income."
        ),
    },
]

FAKE_FINDINGS = {
    "FAKE_SAMPLE_DATA": True,
    "targets": {"grade_level": "3-5", "max_sentence_words": "15-20"},
    "blocks": [
        {
            "block_id": "p-1",
            "word_count": 66,
            "reading_grade": 12.4,
            "long_sentences": [
                {
                    "text": (
                        "Students compare different ways that consumers can get value for their money when "
                        "spending, such as using reward programs or taking advantage of sales."
                    ),
                    "word_count": 24,
                },
                {
                    "text": (
                        "Students investigate the concepts of simple and compound interest using technology, "
                        "(for example, a spreadsheet program) and explain how interest affects long-term "
                        "financial planning."
                    ),
                    "word_count": 24,
                },
            ],
            "difficult_words": ["consumers", "compound", "technology"],
        },
        {
            "block_id": "p-2",
            "word_count": 64,
            "reading_grade": 6.1,
            "long_sentences": [],
            "difficult_words": ["limited", "income", "community"],
        },
    ],
}

FAKE_LAYOUT_METRICS = {
    "FAKE_SAMPLE_DATA": True,
    "targets": {"min_line_height": 1.5, "min_font_size_px": 16, "max_line_length_chars": 70},
    "blocks": [
        {"block_id": "p-1", "font_size_px": 14, "line_height": 1.2, "line_length_chars": 96},
        {"block_id": "p-2", "font_size_px": 14, "line_height": 1.2, "line_length_chars": 96},
    ],
}
