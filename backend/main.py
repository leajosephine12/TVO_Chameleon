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
import re
from pathlib import Path

from accessibility_metrics import analyze_text, structure_checks
from accessibility_metrics.judgement import TEXT_JUDGEMENT, VISION_JUDGEMENT
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app import adaptation_engine as engine
from app.adaptation_engine import _index_blocks
from app.model.adapted_ui import generate_adapted_ui
from app.model.adapted_renderer import apply_adapted_spec, block_text, visible_text
from app.model.adapted_ui_spec import parse_css
from app.model.client import ModelCallError
from app.model.config import ModelConfigError, load_env_file
from app.model.layout_recs import generate_layout_recommendations
from app.model.runner import ModelOutputError
from app.model.text_recs import generate_text_recommendations
from app.schemas import Recommendation

load_env_file(Path(__file__).resolve().parents[1] / "dyslexia_engine" / ".env")

PROSE_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote"}

app = FastAPI(title="chameleon-backend")


def _text_blocks(html: str) -> list[dict]:
    """Same block ids the engine uses (<tag>-<n>), filtered to prose with text."""
    index = _index_blocks(BeautifulSoup(html, "html.parser"))
    return [
        {"block_id": bid, "text": visible_text(tag), "kind": tag.name}
        for bid, tag in index.items()
        if tag.name in PROSE_TAGS and visible_text(tag)
    ]


def _model_blocks(html: str, findings: list[dict], prose_blocks: list[dict]) -> list[dict]:
    """Return prose plus DOM targets for the structural findings Call 1 can fix."""
    supported = {"S3", "J5", "J11", "J12", "J14"}
    wanted = {f["block_id"] for f in findings if f.get("metric_id") in supported}
    index = _index_blocks(BeautifulSoup(html, "html.parser"))
    blocks = {b["block_id"]: b for b in prose_blocks}
    for block_id in wanted:
        tag = index.get(block_id)
        if tag is None:
            continue
        blocks[block_id] = {"block_id": block_id, "text": block_text(tag), "kind": tag.name}
    return list(blocks.values())


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

    model_blocks = _model_blocks(html, findings, blocks)
    if model_blocks:
        try:
            recs += generate_text_recommendations(
                model_blocks, {"findings": findings}, start_id=len(recs) + 1,
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


_ENGINE_EVIDENCE = re.compile(r"^Level \d+ guideline")


def _is_css(r: Recommendation) -> bool:
    try:
        parse_css(r.suggestion)
        return True
    except ValueError:
        return False


@app.post("/adapted")
def adapted(req: AdaptRequest):
    # Split by evidence, not type: a model rec may reuse an engine type name
    # (Gemma emitted "typography"), which must not trigger the engine's whole stylesheet.
    # Engine recs cite "Level <n> guideline(s) ..." — any level, so level 2 routes here too.
    engine_recs = [r for r in req.recommendations if _ENGINE_EVIDENCE.match(r.evidence)]
    model_recs = [r for r in req.recommendations if not _ENGINE_EVIDENCE.match(r.evidence)]
    result = engine.apply_level1(req.html, engine_recs)

    skipped = list(result.skipped)
    if any(r.status in ("accepted", "edited") for r in model_recs):
        soup = BeautifulSoup(result.adapted_html, "html.parser")
        index = _index_blocks(soup)
        blocks = [
            {"block_id": b, "text": block_text(t), "kind": t.name, "alt": t.get("alt", "")}
            for b, t in index.items()
        ]
        # CSS suggestions are layout recs (call 2); everything else is a text rewrite (call 1)
        spec = generate_adapted_ui(
            [r for r in model_recs if not _is_css(r)],
            [r for r in model_recs if _is_css(r)],
            blocks,
        )
        skipped += [s.id for s in spec.skipped]
        rendered = apply_adapted_spec(str(soup), spec.spec)
        result.adapted_html = rendered.html
        failed_targets = {
            (spec.spec.changes[i].block_id, spec.spec.changes[i].action == "set_style")
            for i in rendered.skipped
        }
        for r in model_recs:
            if r.status not in ("accepted", "edited") or r.id in skipped:
                continue
            if (r.block_id, _is_css(r)) in failed_targets:
                skipped.append(r.id)
            else:
                result.applied.append(r.id)

    return {
        "adapted_html": result.adapted_html,
        "injected_css": result.injected_css,
        "applied": result.applied,
        "skipped": skipped,
        "contrast_ratio": result.contrast_ratio,
    }
