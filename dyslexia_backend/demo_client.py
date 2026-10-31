"""Demo: recommend -> user decides -> apply only what was accepted.

  frontend (iframe HTML) -> backend/AI (FastMCP Client) -> FastMCP server -> Python engine

In the real system the UI shows each recommendation and the backend records the
user's accept / deny / edit. Here we simulate those decisions.

Run:
    python demo_client.py                              # in-memory, no server needed
    python demo_client.py http://127.0.0.1:8000/mcp    # against `python -m app.main --http`
"""
import asyncio
import json
import sys
from pathlib import Path

from fastmcp import Client

from app.main import mcp

ROOT = Path(__file__).parent


async def run(target) -> None:
    html = (ROOT / "demo" / "sample_iframe.html").read_text()

    async with Client(target) as client:
        print("== Tools ==")
        for tool in await client.list_tools():
            print(f"  - {tool.name}")

        print("\n== 1. analyze_html -> recommendations ==")
        res = await client.call_tool("analyze_html", {"html": html})
        recs = res.structured_content["recommendations"]
        for r in recs:
            print(f"  {r['id']:<4} {r['block_id']:<7} {r['type']:<15} {r['severity']:<7} {r['status']}")
        print("\n  Example recommendation (shared format):")
        print(json.dumps(recs[0], indent=2))

        # --- simulated UI decisions (Interface 3: POST /recommendations/{id}/decision) ---
        for r in recs:
            r["status"] = "denied" if r["type"] == "layout" else "accepted"
        denied = [r["id"] for r in recs if r["status"] == "denied"]
        print(f"\n== 2. User accepts everything except the layout rule (denied: {denied}) ==")

        print("\n== 3. apply_recommendations ==")
        out = (await client.call_tool("apply_recommendations", {"html": html, "recommendations": recs})).structured_content
        print(f"  applied: {out['applied']}")
        print(f"  skipped: {out['skipped']}")
        print(f"  contrast ratio: {out['contrast_ratio']}")
        out_path = ROOT / "demo" / "sample_adapted.html"
        out_path.write_text(out["adapted_html"])
        print(f"  wrote {out_path}")

        print("\n== 4. analyze_html on the adapted page: only the denied rule remains ==")
        again = (await client.call_tool("analyze_html", {"html": out["adapted_html"]})).structured_content
        for r in again["recommendations"]:
            print(f"  {r['id']:<4} {r['block_id']:<7} {r['type']:<15} {r['status']}")


if __name__ == "__main__":
    asyncio.run(run(sys.argv[1] if len(sys.argv) > 1 else mcp))