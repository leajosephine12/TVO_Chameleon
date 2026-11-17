"""
backend/main.py
Chameleon backend: the one HTTP service the frontend talks to.

Wraps the dyslexia_engine as a library (their readme: "The engine is plain
Python, so it can be called directly too"), so there is no second server.

POST /analyze {html, level}                  -> engine recs (level 1 or 2), all status "pending"
POST /adapted {html, level, recommendations} -> applies only accepted/edited ones, returns adapted HTML

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

from app import adaptation_engine as dys_engine
from app.schemas import Recommendation

try:  # same .env the engine uses for level 2 (same approach as run_demo_l1and2.py)
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / "dyslexia_engine" / ".env")
except ImportError:
    pass

PROSE_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote"}

app = FastAPI(title="chameleon-backend")


def _index_blocks(soup: BeautifulSoup) -> dict:
    """Block ids '<tag>-<n>' (n counts per tag, in document order). Same html in -> same ids."""
    index, counters = {}, {}
    for tag in soup.find_all(True):
        counters[tag.name] = counters.get(tag.name, 0) + 1
        index[f"{tag.name}-{counters[tag.name]}"] = tag
    return index


def visible_text(tag) -> str:
    return " ".join(tag.get_text(" ", strip=True).split())


def _text_blocks(index: dict) -> list[dict]:
    """Block ids '<tag>-<n>', filtered to prose with text."""
    return [
        {"block_id": bid, "text": visible_text(tag), "kind": tag.name}
        for bid, tag in index.items()
        if tag.name in PROSE_TAGS and visible_text(tag)
    ]


def _to_dict(obj):
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, list):
        return [_to_dict(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    return obj


def _find_block_list(data):
    """Find the list of adapted blocks (dicts with block_id) inside a Level 2 result."""
    if isinstance(data, list) and data and all(isinstance(x, dict) and "block_id" in x for x in data):
        return data
    if isinstance(data, dict):
        for v in data.values():
            found = _find_block_list(v)
            if found:
                return found
    if isinstance(data, list):
        for v in data:
            found = _find_block_list(v)
            if found:
                return found
    return None


# Reviewer attention is the budget now, not model speed (the 4 was tuned for local Gemma).
MAX_RECS = int(os.environ.get("MAX_RECOMMENDATIONS", "8"))


class AnalyzeRequest(BaseModel):
    html: str = ""  # optional when render=true (the rendered page's HTML is used)
    url: str | None = None  # used by URL-dependent metrics (N2) and required for render
    render: bool = False  # render with Playwright: layout metrics + axe findings
    level: int = 1  # 1 = CSS representation, 2 = plain-language text


class AdaptRequest(BaseModel):
    html: str
    recommendations: list[Recommendation]
    level: int = 1


def _check_level(level: int) -> None:
    if level not in dys_engine.SUPPORTED_LEVELS:
        raise HTTPException(status_code=422, detail=f"level must be one of {list(dys_engine.SUPPORTED_LEVELS)}")


@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    _check_level(req.level)
    rendered = None
    if req.render:
        if not req.url:
            raise HTTPException(status_code=422, detail="render=true needs a url")
        from accessibility_metrics.rendered import rendered_checks  # optional Playwright dependency

        rendered = rendered_checks(req.url)
    html = req.html or (rendered["html"] if rendered else "")
    if not html:
        raise HTTPException(status_code=422, detail="send html, or render=true with a url")

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
        except Exception as e:  # model/config problem: level 1-style recs still work, UI can show this
            model_errors.append(f"{type(e).__name__}: {e}")

    return {"level": req.level, "recommendations": recs,
            "model_error": "; ".join(model_errors) or None, "findings": findings}


@app.post("/adapted")
def adapted(req: AdaptRequest):
    _check_level(req.level)
    # The dys_engine treats "pending" as accepted and keeps "denied" denied.
    recs = [r for r in req.recommendations if r.status in ("accepted", "edited", "pending")]

    if req.level == 1:
        result = dys_engine.apply(1, html=req.html, accepted=recs)
        return {
            "adapted_html": result.adapted_html,
            "injected_css": result.injected_css,
            "applied": result.applied,
            "skipped": list(result.skipped),
            "contrast_ratio": result.contrast_ratio,
        }

    # Level 2: dys_engine rewrites the text blocks, then we write the new text back into the HTML.
    soup = BeautifulSoup(req.html, "html.parser")
    index = _index_blocks(soup)
    blocks = _text_blocks(index)
    if not blocks:
        raise HTTPException(status_code=422, detail="no prose text found for level 2")
    try:
        result = dys_engine.apply(2, blocks=blocks, accepted=recs)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"level 2 failed: {type(e).__name__}: {e}")

    data = _to_dict(result)
    before = {b["block_id"]: b["text"] for b in blocks}
    changed = []
    for nb in _find_block_list(data) or []:
        bid = nb["block_id"]
        after = nb.get("text") or nb.get("adapted_text") or nb.get("new_text") or ""
        tag = index.get(bid)
        if tag is None or not after or after == before.get(bid):
            continue
        tag.clear()  # inline markup inside a rewritten block is replaced by plain text
        tag.append(after)
        changed.append(bid)

    return {
        "adapted_html": str(soup),
        "changed_blocks": changed,
        "applied": data.get("applied") if isinstance(data, dict) else None,
        "skipped": data.get("skipped", []) if isinstance(data, dict) else [],
        "result": data,
    }