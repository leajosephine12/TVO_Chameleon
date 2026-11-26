"""
backend/main.py
Chameleon backend: the one HTTP service the frontend talks to.

Wraps the dyslexia_engine as a library (their readme: "The engine is plain
Python, so it can be called directly too"), so there is no second server.

Two audiences, two pairs of endpoints. They are kept apart so the review UI can show them in separate
tabs (see "Why two pairs of endpoints" in docs/architecture.md).

Dyslexia version:
POST /analyze {html, level}                  -> engine recs (level 1 = CSS, level 2 = plain-language text), all "pending"
POST /adapted {html, level, recommendations} -> applies only accepted/edited ones, returns adapted HTML

General accessibility version (backend/genui):
POST /analyze_general {html}                  -> typed page changes for the general metrics, all "pending"
POST /adapted_general {html, recommendations} -> applies the accepted/edited typed changes

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
import logging

from accessibility_metrics import analyze_text, structure_checks
from accessibility_metrics.judgement import TEXT_JUDGEMENT, VISION_JUDGEMENT

from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app import adaptation_engine as dys_engine
from app.levels.level1_representation import _index_blocks
# the path might be changed in the future but the function is used for sure
from app.model.level3_future.adapted_renderer import apply_adapted_spec, block_text, visible_text
from app.model.level3_future.adapted_ui import generate_adapted_ui
from app.model.level3_future.adapted_ui_spec import parse_css
from app.schemas import Recommendation

from app.model.client import ModelCallError
from app.model.config import ModelConfigError, load_env_file
from app.model.log import enable_timing_logs
from app.model.runner import ModelOutputError

from genui import A11yRecommendation, analyze_general, apply_general


logger = logging.getLogger(__name__)
_env_path = Path(__file__).resolve().parents[1] / "dyslexia_engine" / ".env"
if _env_path.is_file():
    load_env_file(_env_path)
else:
    logger.warning(".env not found at %s; Level 2 settings may be missing", _env_path)
enable_timing_logs()  # one line per model call in the terminal


PROSE_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote"}
app = FastAPI(title="chameleon-backend")


def _text_blocks(index: dict) -> list[dict]:
    """Block ids '<tag>-<n>', filtered to prose with text."""
    return [
        {"block_id": bid, "text": visible_text(tag), "kind": tag.name}
        for bid, tag in index.items()
        if tag.name in PROSE_TAGS and visible_text(tag)
    ]


# Reviewer attention is the budget now, not model speed (the 4 was tuned for local Gemma).
MAX_RECS = int(os.environ.get("MAX_RECOMMENDATIONS", "8"))


class AnalyzeRequest(BaseModel):
    html: str = ""  # optional when render=true (the rendered page's HTML is used)
    url: str | None = None  # used by URL-dependent metrics (N2) and required for render
    level: int = 1  # 1 = CSS representation, 2 = plain-language text
    render: bool = False  # render with Playwright: layout metrics + axe + screenshot + model call 2
    # Only the dyslexia rule engine, no model call. The review UI sends this: the model's text
    # recommendations come from the general metrics, which it gets from /analyze_general instead.
    rules_only: bool = False

class AdaptRequest(BaseModel):
    html: str
    recommendations: list[Recommendation]
    level: int = 1


def _check_level(level: int) -> None:
    if level not in dys_engine.SUPPORTED_LEVELS:
        raise HTTPException(status_code=422, detail=f"level must be one of {list(dys_engine.SUPPORTED_LEVELS)}")


class GeneralAdaptRequest(BaseModel):
    html: str
    recommendations: list[A11yRecommendation]


def _page(req: AnalyzeRequest) -> tuple[str, dict | None]:
    """The HTML to analyse and, when render=true, what the rendered page measured."""
    rendered = None
    if req.render:
        if not req.url:
            raise HTTPException(status_code=422, detail="render=true needs a url")
        from accessibility_metrics.rendered import rendered_checks  # optional Playwright dependency

        rendered = rendered_checks(req.url)
    html = req.html or (rendered["html"] if rendered else "")
    if not html:
        raise HTTPException(status_code=422, detail="send html, or render=true with a url")
    return html, rendered


@app.post("/analyze_general")
def analyze_general_page(req: AnalyzeRequest):
    layout_error = None
    try:
        html, rendered = _page(req)
    except HTTPException:
        raise
    except Exception as e:  # no Playwright, or the page could not be opened: the text and structure checks still run
        if not req.html:
            raise HTTPException(status_code=502, detail=f"The page could not be rendered: {e}")
        html, rendered, layout_error = req.html, None, (str(e).splitlines() or [type(e).__name__])[0]
    return {**analyze_general(html, req.url, rendered), "layout_error": layout_error}


@app.post("/adapted_general")
def adapted_general(req: GeneralAdaptRequest):
    return apply_general(req.html, req.recommendations)


@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    _check_level(req.level)
    html, rendered = _page(req)
    if req.rules_only:
        recs = dys_engine.analyze(1, html=html).recommendations
        return {"level": 1, "recommendations": recs, "model_error": None, "findings": []}
    index = _index_blocks(BeautifulSoup(html, "html.parser"))
    blocks = _text_blocks(index)
    findings = analyze_text(blocks)["findings"] + structure_checks(html, url=req.url)["findings"]
    if rendered:
        findings += rendered["findings"]

    recs = []
    model_errors = []
    if req.level == 1:
        recs = dys_engine.analyze(1, html=html).recommendations
    elif blocks:
        try:
            recs = dys_engine.analyze(2, blocks=blocks, max_recommendations=MAX_RECS).recommendations
        except (ModelConfigError, ModelCallError, ModelOutputError) as e:
            model_errors.append(str(e))
            recs = []

    return {"level": req.level, "recommendations": recs,
            "model_error": "; ".join(model_errors) or None, "findings": findings}


_ENGINE_EVIDENCE = re.compile(r"^(L\d+\.\d+|Level \d+ guideline)")


def _is_css(r: Recommendation) -> bool:
    try:
        parse_css(r.suggestion)
        return True
    except ValueError:
        return False


@app.post("/adapted")
def adapted(req: AdaptRequest):
    _check_level(req.level)
    # Only apply what the user accepted (or edited); pending and denied are left alone.
    recs = [r for r in req.recommendations if r.status in ("accepted", "edited")]
    if req.level == 1:
        # Split by evidence, not type: a model rec may reuse an engine type name,
        # which must not trigger the engine's whole stylesheet.
        engine_recs = [r for r in recs if _ENGINE_EVIDENCE.match(r.evidence)]
        model_recs = [r for r in recs if not _ENGINE_EVIDENCE.match(r.evidence)]
        result = dys_engine.apply(1, html=req.html, accepted=engine_recs)

        adapted_html = result.adapted_html
        applied = list(result.applied)
        skipped = list(result.skipped)

        if model_recs:
            soup = BeautifulSoup(adapted_html, "html.parser")
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
            adapted_html = rendered.html
            # At most one content change and one set_style per block, so
            # (block_id, is_style) uniquely identifies a recommendation.
            failed_targets = {
                (spec.spec.changes[i].block_id, spec.spec.changes[i].action == "set_style")
                for i in rendered.skipped
            }
            for r in model_recs:
                if r.id in skipped:
                    continue
                if (r.block_id, _is_css(r)) in failed_targets:
                    skipped.append(r.id)
                else:
                    applied.append(r.id)

        return {
            "adapted_html": adapted_html,
            "injected_css": result.injected_css,
            "applied": applied,
            "skipped": skipped,
            "contrast_ratio": result.contrast_ratio,
        }

    # Level 2: dys_engine rewrites the text blocks, then we write the new text back into the HTML.
    soup = BeautifulSoup(req.html, "html.parser")
    index = _index_blocks(soup)
    blocks = _text_blocks(index)
    if not blocks:
        raise HTTPException(status_code=422, detail="no prose text found for level 2")
    result = dys_engine.apply(2, blocks=blocks, accepted=recs)

    before = {b["block_id"]: b["text"] for b in blocks}
    changed = []
    skipped_blocks = []
    for nb in result.blocks:
        tag = index.get(nb.block_id)
        if tag is None:
            skipped_blocks.append({"block_id": nb.block_id, "reason": "block not found in page"})
            continue
        if not nb.text or nb.text == before.get(nb.block_id):
            continue  # nothing to write; not an error, just not applied
        if tag.find(True):
            skipped_blocks.append({"block_id": nb.block_id, "reason": "block contains links or inline formatting"})
            continue
        tag.string = nb.text
        changed.append(nb.block_id)

    # "applied" = recs whose block was really rewritten in the HTML
    changed_ids = set(changed)
    rec_block = {r.id: r.block_id for r in recs}
    applied = [rid for rid in result.applied if rec_block.get(rid) in changed_ids]

    return {
        "adapted_html": str(soup),
        "changed_blocks": changed,
        "applied": applied,
        "skipped": [s.model_dump() for s in result.skipped] + skipped_blocks,
    }