"""
dyslexia_engine/app/main.py
HTTP layer for the DYSLEXIA ENGINE ONLY (levels 1 and 2).

Owner: dyslexia side. This service knows nothing about other engines.

-------------------------------------------------------------------------------
THIS SERVICE'S API (port 8001)
-------------------------------------------------------------------------------
POST /analyze {level, html | blocks, enabled_rules?, max_recommendations?}
    -> AnalyzeResult {level, recommendations[], findings}
       Nothing is changed. Every recommendation comes back with status "pending".

POST /adapted {level, html | blocks, recommendations[]}
    -> level 1: AdaptResult {adapted_html, injected_css, applied[], skipped[], contrast_ratio}
       level 2: Level2ApplyResult
       Only recommendations with status "accepted" or "edited" are applied.

Input rules
  - level 1 works on an HTML string. Block ids are "<tag>-<n>", e.g. "p-4".
  - level 2 works on text blocks: [{"block_id", "text"}].
  - Send the SAME html / blocks to /analyze and /adapted, or block ids will not match.
  - Errors: 422 = bad request (unsupported level, missing html/blocks),
            502 = model unavailable (level 2 calls an LLM).

-------------------------------------------------------------------------------
WHAT backend/main.py MUST DO (the gateway; the frontend talks ONLY to it)
-------------------------------------------------------------------------------
backend/main.py is the single entry point for the frontend. It combines this
service with general_accessibility_engine. It must contain NO engine logic.

1. Call each engine over HTTP. Do NOT import code from dyslexia_engine or
   general_accessibility_engine. Both use a top-level package called `app`,
   so importing one into the other's process will clash. Run each engine as
   its own process on its own port, e.g.:
       dyslexia_engine                -> http://localhost:8001
       general_accessibility_engine   -> its own port (see that engine's README)
       backend (this gateway)         -> the port the frontend uses

2. POST /analyze: forward the page to every engine that should run, collect
   their recommendations, and return one merged list to the frontend.
   If one engine fails, still return the others and report the failure in a
   field such as "engine_errors" instead of failing the whole request.

3. Keep recommendation ids unique after merging. Each engine numbers its own
   recommendations "r1", "r2", ..., so ids WILL collide. The gateway must tag
   each recommendation with the engine it came from (e.g. a "source" field, or
   an id prefix like "dys:r3") and remember it.

4. POST /adapted: split the accepted/edited recommendations by source engine,
   send each engine only its own, and combine the results. Route by SOURCE,
   not by the `evidence` text. (The old "Level N guideline" evidence-prefix
   check no longer works; evidence now starts with guideline ids such as
   "L1.1.7: Scope. (2023) ...".) Strip any gateway prefix before forwarding.

5. Combining adapted HTML from several engines: each engine edits the page
   and returns its own adapted_html. Agree on an order (chain them, feeding
   one engine's output into the next) and keep block ids valid between steps.
   The dyslexia level 1 engine adds a <style data-dyslexia-adapt> tag and
   rewrites <i>/<em>/<u>, which can shift later "<tag>-<n>" ids, so run
   id-based engines BEFORE it or re-analyse after it.

6. Pass the frontend's `level`, `html`, `blocks`, `enabled_rules` and
   `max_recommendations` through to this service unchanged, and return its
   errors (422 / 502) to the frontend without hiding the reason.

7. Gateway-only concerns live in backend/main.py: CORS, auth, timeouts
   (model calls are slow, use a generous timeout), and any URL rendering or
   screenshot step that is not part of the dyslexia engine.

Run this service (from the dyslexia_engine folder):
    uv run uvicorn app.main:app --port 8001
"""
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from . import adaptation_engine as engine
from .model.client import ModelCallError
from .model.config import ModelConfigError, load_env_file
from .model.runner import ModelOutputError
from .schemas import Recommendation

load_env_file(Path(__file__).resolve().parents[1] / ".env")

MODEL_ERRORS = (ModelConfigError, ModelCallError, ModelOutputError)

app = FastAPI(title="chameleon-backend")


class AnalyzeRequest(BaseModel):
    level: int = 1
    html: str | None = None        # level 1
    blocks: list[dict] | None = None  # level 2: [{"block_id", "text"}]
    enabled_rules: list[str] | None = None
    max_recommendations: int | None = None


class AdaptRequest(BaseModel):
    level: int = 1
    html: str | None = None
    blocks: list[dict] | None = None
    recommendations: list[Recommendation]


@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    try:
        return engine.analyze(
            req.level,
            html=req.html,
            blocks=req.blocks,
            enabled_rules=req.enabled_rules,
            max_recommendations=req.max_recommendations,
        )
    except ValueError as e:                 # unsupported level / missing html or blocks
        raise HTTPException(status_code=422, detail=str(e))
    except MODEL_ERRORS as e:               # level 2 calls the model
        raise HTTPException(status_code=502, detail=f"Model unavailable: {e}")


@app.post("/adapted")
def adapted(req: AdaptRequest):
    # Only what the user accepted or edited is applied; pending and denied are dropped.
    accepted = [r for r in req.recommendations if r.status in ("accepted", "edited")]
    try:
        return engine.apply(req.level, accepted=accepted, html=req.html, blocks=req.blocks)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except MODEL_ERRORS as e:
        raise HTTPException(status_code=502, detail=f"Model unavailable: {e}")