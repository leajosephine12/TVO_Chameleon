"""FastMCP server: exposes the dyslexia engine as MCP tools (JSON in, JSON out, no model inside).

Run (stdio, for MCP clients / AI models):     python -m app.main
Run (HTTP, for the backend / other services): python -m app.main --http
"""
import sys

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from . import adaptation_engine as engine
from .guidelines import get_guidelines as _get_guidelines
from .schemas import AdaptResult, AnalyzeResult, GuidelinesResponse, Recommendation

mcp = FastMCP(
    name="dyslexia-adapter",
    instructions=(
        "Dyslexia adaptation for education web content. Flow: analyze_html returns recommendations "
        "(status 'pending'); the user accepts, denies or edits each; apply_recommendations applies "
        "only the accepted or edited ones."
    ),
)


def _require_level(level: int) -> None:
    if level != 1:
        raise ToolError(f"Level {level} is not implemented yet. Only level 1 is available.")


@mcp.tool
def get_guidelines(level: int = 1) -> GuidelinesResponse:
    """Return the dyslexia guidelines for a level so the caller can cite them."""
    _require_level(level)
    return GuidelinesResponse(level=level, guidelines=_get_guidelines(level))


@mcp.tool
def analyze_html(html: str, level: int = 1) -> AnalyzeResult:
    """Check HTML against the guidelines and return recommendations (all status 'pending'). Changes nothing."""
    _require_level(level)
    return AnalyzeResult(level=level, recommendations=engine.analyze_level1(html))


@mcp.tool
def apply_recommendations(html: str, recommendations: list[Recommendation]) -> AdaptResult:
    """Apply only recommendations whose status is 'accepted' or 'edited'. Send the same HTML that was analyzed."""
    return engine.apply_level1(html, recommendations)


@mcp.resource("guidelines://level1")
def level1_resource() -> GuidelinesResponse:
    """Level 1 guidelines as a readable resource."""
    return GuidelinesResponse(level=1, guidelines=_get_guidelines(1))


if __name__ == "__main__":
    if "--http" in sys.argv:
        mcp.run(transport="http", host="127.0.0.1", port=8000)
    else:
        mcp.run()