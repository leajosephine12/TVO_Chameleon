"""Bucket-4 judgement extension: labeled judgements pass, unknown metric ids are rejected."""
import json

import pytest

from app.model.config import ModelConfig
from app.model.runner import ModelOutputError
from app.model.text_recs import generate_text_recommendations

CONFIG = ModelConfig(mock=False, model_name="test")  # real-mode checks, fake caller, no network
BLOCKS = [{"block_id": "p-1", "text": "Students complete the enrollment during photosynthesis week."}]
FINDINGS = {"findings": []}
CHECKS = {"T9": "Jargon a Grade 3-5 reader would need defined. Quote the term."}


def reply(evidence):
    return json.dumps({"recommendations": [{
        "id": "r1", "block_id": "p-1", "type": "T9",
        "original": "enrollment", "suggestion": "enrollment (signing up)",
        "rationale": "A young reader will not know this word.",
        "evidence": evidence, "severity": "low", "status": "pending",
    }]})


def caller_with(evidence):
    return lambda messages, **kw: reply(evidence)


def test_registered_judgement_passes():
    recs = generate_text_recommendations(
        BLOCKS, FINDINGS, config=CONFIG, judgement_checks=CHECKS, max_retries=0,
        caller=caller_with("model judgement / T9"),
    )
    assert [r.evidence for r in recs] == ["model judgement / T9"]


def test_unknown_judgement_id_rejected():
    with pytest.raises(ModelOutputError):
        generate_text_recommendations(
            BLOCKS, FINDINGS, config=CONFIG, judgement_checks=CHECKS, max_retries=0,
            caller=caller_with("model judgement / Z9"),
        )


def test_checklist_lands_in_prompt():
    captured = {}

    def caller(messages, **kw):
        captured["system"] = messages[0]["content"]
        return reply("model judgement / T9")

    generate_text_recommendations(BLOCKS, FINDINGS, config=CONFIG, judgement_checks=CHECKS,
                                  max_retries=0, caller=caller)
    assert "Judgement checks" in captured["system"] and "T9" in captured["system"]


def test_no_checklist_no_prompt_section():
    captured = {}

    def caller(messages, **kw):
        captured["system"] = messages[0]["content"]
        return json.dumps({"recommendations": []})

    generate_text_recommendations(BLOCKS, FINDINGS, config=CONFIG, max_retries=0, caller=caller)
    assert "Judgement checks" not in captured["system"]
