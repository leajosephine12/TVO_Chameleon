"""Chameleon backend (placeholder).

Owns the agent loop: calls the model, executes requested tools against the
local MCP server (Interface 2), feeds results back, loops until done.

Model is Claude API for now. The loop shape (messages + tools + tool_results)
is the same one an OpenAI-compatible local model (Ollama/vLLM) uses, so
swapping later means replacing the `claude.messages.create` call, not the loop.

Config: ANTHROPIC_API_KEY (env/ant profile), MODEL_NAME, MCP_URL.

Run: uv run uvicorn main:app --port 8001
"""

import json
import os
from typing import Literal

import anthropic
from fastapi import FastAPI, HTTPException
from fastmcp import Client
from pydantic import BaseModel

MCP_URL = os.environ.get("MCP_URL", "http://localhost:8000/mcp")
MODEL_NAME = os.environ.get("MODEL_NAME", "claude-opus-5-5")

SYSTEM = """You analyze web pages for dyslexia accessibility.

Use the available tools to fetch the page and gather findings, then produce
recommendations. Respond with ONLY a JSON array of recommendation objects in
exactly this shape, no prose, no markdown fences:

[
  {
    "id": "r1",
    "block_id": "p-4",
    "type": "long_sentence",
    "original": "...",
    "suggestion": "...",
    "rationale": "34 words; Grade 3-5 target <= 15-20",
    "evidence": "readability tool / W3C COGA",
    "severity": "medium",
    "status": "pending"
  }
]
"""

app = FastAPI(title="chameleon-backend")
claude = anthropic.AsyncAnthropic()

# ponytail: in-memory store, lost on restart. Move to a DB when persistence matters.
decisions: dict[str, dict] = {}


class AnalyzeRequest(BaseModel):
    url: str


class DecisionRequest(BaseModel):
    decision: Literal["accept", "deny", "edit"]
    edited_text: str | None = None


@app.post("/analyze")
async def analyze(req: AnalyzeRequest):
    async with Client(MCP_URL) as mcp:
        tools = [
            {
                "name": t.name,
                "description": t.description or "",
                "input_schema": t.inputSchema,
            }
            for t in await mcp.list_tools()
        ]
        messages = [
            {"role": "user", "content": f"Analyze this page for dyslexia accessibility: {req.url}"}
        ]
        while True:
            response = await claude.messages.create(
                model=MODEL_NAME,
                max_tokens=16000,
                system=SYSTEM,
                tools=tools,
                messages=messages,
            )
            if response.stop_reason == "refusal":
                detail = response.stop_details.explanation if response.stop_details else "model refused"
                raise HTTPException(status_code=502, detail=f"Model refused: {detail}")
            if response.stop_reason != "tool_use":
                break
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                try:
                    result = await mcp.call_tool(block.name, block.input)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result.data),
                        }
                    )
                except Exception as e:
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": str(e),
                            "is_error": True,
                        }
                    )
            messages.append({"role": "user", "content": tool_results})

    text = next((b.text for b in response.content if b.type == "text"), "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    try:
        recommendations = json.loads(text)
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail=f"Model did not return JSON: {text[:500]}")
    return {"url": req.url, "recommendations": recommendations}


@app.post("/recommendations/{rec_id}/decision")
async def decide(rec_id: str, req: DecisionRequest):
    decisions[rec_id] = req.model_dump()
    return {"id": rec_id, **decisions[rec_id]}


@app.get("/adapted")
async def adapted(url: str):
    # ponytail: placeholder. Real version applies accepted changes to the page
    # (model call #3, generate_adapted_ui) once that pipeline exists.
    return {"url": url, "decisions": decisions, "html": None}
