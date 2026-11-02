"""Chameleon backend: the one HTTP service the frontend talks to.

Wraps the dyslexia_engine as a library (their readme: "The engine is plain
Python, so it can be called directly too"), so there is no second server.

POST /analyze {html}                  -> rule-engine recs + model text recs, all status "pending"
POST /adapted {html, recommendations} -> applies only accepted/edited ones, returns adapted HTML

Model = anything OpenAI-format via dyslexia_engine's own client. For Claude:
    MODEL_BASE_URL=https://api.anthropic.com/v1
    MODEL_NAME=claude-sonnet-5-5
    MODEL_API_KEY=<ANTHROPIC_API_KEY>
Or MODEL_MOCK=1 for no model, or Ollama per dyslexia_engine/.env.example.

Run: uv run uvicorn main:app --port 8001
"""
import os
from pathlib import Path

from accessibility_metrics import analyze_text, structure_checks
from accessibility_metrics.judgement import TEXT_JUDGEMENT, VISION_JUDGEMENT
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app import adaptation_engine as engine
from app.adaptation_engine import ELEMENT_TYPES, _index_blocks
from app.guidelines import PAGE_RULES
from app.model.adapted_ui import generate_adapted_ui
from app.model.client import ModelCallError
from app.model.config import ModelConfigError, load_env_file
from app.model.layout_recs import generate_layout_recommendations
from app.model.runner import ModelOutputError
from app.model.text_recs import generate_text_recommendations
from app.schemas import Recommendation

load_env_file(Path(__file__).resolve().parents[1] / "dyslexia_engine" / ".env")

ENGINE_TYPES = ELEMENT_TYPES | set(PAGE_RULES)
PROSE_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote"}

app = FastAPI(title="chameleon-backend")


def _text_blocks(html: str) -> list[dict]:
    """Same block ids the engine uses (<tag>-<n>), filtered to prose with text."""
    index = _index_blocks(BeautifulSoup(html, "html.parser"))
    return [
        {"block_id": bid, "text": tag.get_text(), "kind": tag.name}
        for bid, tag in index.items()
        if tag.name in PROSE_TAGS and tag.get_text().strip()
    ]


# Reviewer attention is the budget now, not model speed (the 4 was tuned for local Gemma).
MAX_RECS = int(os.environ.get("MAX_RECOMMENDATIONS", "8"))
MODEL_ERRORS = (ModelConfigError, ModelCallError, ModelOutputError)


class AnalyzeRequest(BaseModel):
    html: str = ""  # optional when render=true (the rendered page's HTML is used)
    url: str | None = None  # used by URL-dependent metrics (N2) and required for render
    render: bool = False  # render with Playwright: layout metrics + axe + screenshot + model call 2


class AdaptRequest(BaseModel):
    html: str
    recommendations: list[Recommendation]


@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    rendered = None
    if req.render:
        if not req.url:
            raise HTTPException(status_code=422, detail="render=true needs a url")
        from accessibility_metrics.rendered import rendered_checks  # optional Playwright dependency

        rendered = rendered_checks(req.url)
    html = req.html or (rendered["html"] if rendered else "")
    if not html:
        raise HTTPException(status_code=422, detail="send html, or render=true with a url")

    recs = engine.analyze_level1(html)
    model_errors = []
    blocks = _text_blocks(html)
    findings = analyze_text(blocks)["findings"] + structure_checks(html, url=req.url)["findings"]
    if rendered:
        findings += rendered["findings"]

    if blocks:
        try:
            recs += generate_text_recommendations(
                blocks, {"findings": findings}, start_id=len(recs) + 1,
                max_recommendations=MAX_RECS, judgement_checks=TEXT_JUDGEMENT,
            )
        except MODEL_ERRORS as e:
            model_errors.append(str(e))  # engine recs still ship; the UI can show the model was unavailable
    if rendered:
        try:
            recs += generate_layout_recommendations(
                rendered["screenshot"], {"blocks": rendered["metrics"]["blocks"]},
                start_id=len(recs) + 1, max_recommendations=MAX_RECS, judgement_checks=VISION_JUDGEMENT,
            )
        except MODEL_ERRORS as e:
            model_errors.append(str(e))

    return {"level": 1, "recommendations": recs,
            "model_error": "; ".join(model_errors) or None, "findings": findings}


@app.post("/adapted")
def adapted(req: AdaptRequest):
    engine_recs = [r for r in req.recommendations if r.type in ENGINE_TYPES]
    model_recs = [r for r in req.recommendations if r.type not in ENGINE_TYPES]
    result = engine.apply_level1(req.html, engine_recs)

    skipped = list(result.skipped)
    if any(r.status in ("accepted", "edited") for r in model_recs):
        soup = BeautifulSoup(result.adapted_html, "html.parser")
        index = _index_blocks(soup)
        blocks = [{"block_id": b, "text": t.get_text()} for b, t in index.items()]
        spec = generate_adapted_ui(model_recs, [], blocks)
        skipped += [s.id for s in spec.skipped]
        for change in spec.spec.changes:
            tag = index.get(change.block_id)
            if tag is None:
                continue
            if change.action == "replace_text":
                # ponytail: replaces the block's text wholesale, dropping inline tags
                # inside it. Fine for prose paragraphs; revisit if blocks carry links.
                tag.clear()
                tag.append(change.value)
            elif change.action == "set_style":
                old = tag.get("style", "").rstrip("; ")
                tag["style"] = f"{old}; {change.value}" if old else change.value
        result.adapted_html = str(soup)
        result.applied = result.applied + [
            r.id for r in model_recs if r.status in ("accepted", "edited") and r.id not in skipped
        ]

    return {
        "adapted_html": result.adapted_html,
        "injected_css": result.injected_css,
        "applied": result.applied,
        "skipped": skipped,
        "contrast_ratio": result.contrast_ratio,
    }
