"""
dyslexia_engine/tests/test_updated_level1and2/run_demo_l1and2.py

Tests if dyslexia_engine/adaptation_engine.py is working correctly

Put this file in the dyslexia_engine/ folder (the one that CONTAINS app/), then run:

    python run_demo.py                 # level 1 + level 2
    python run_demo.py --level 1       # only level 1 (no model call)
    python run_demo.py --level 2       # only level 2 (calls the model, needs .env)
    python run_demo.py --deny 1,3      # deny recommendations 1 and 3 (1-based) to test "denied stays denied"

Make sure to set .env file so that level 2 outputs the right recommendation
"""
import argparse
import json
import traceback
from pathlib import Path

try:  # load .env if python-dotenv is installed (your model/config.py may already do this)
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from app.adaptation_engine import analyze, apply

OUT = Path(__file__).parent / "results"

# --------------------------------------------------------------------------------------
# Sample input
# --------------------------------------------------------------------------------------
SAMPLE_HTML = """<!doctype html>
<html>
<head>
  <title>Photosynthesis</title>
  <style>
    body { font-family: "Times New Roman", serif; font-size: 12px; background: #fff; color: #000; }
    .content { column-count: 2; column-gap: 20px; }
    h1 { font-size: 14px; }
  </style>
</head>
<body>
  <h1>How plants make food</h1>
  <div class="content">
    <p>Photosynthesis is the process <em>by which</em> plants turn sunlight into energy. It takes place in the <u>chloroplasts</u> of each cell.</p>
    <p style="font-style: italic;">Plants need three things: light, water and carbon dioxide.</p>
    <p>Read the <a href="/lesson-2">next lesson</a> to learn about <i>respiration</i>.</p>
  </div>
</body>
</html>
"""

# Level 2 works on text blocks. These are written to trigger several L2 rules:
# jargon, long words, passive voice, foreign phrases, uppercase, silent letters, dashes.
SAMPLE_BLOCKS = [
    {
        "block_id": "p-1",
        "text": "Photosynthesis is utilised by plants in order to facilitate the conversion of sunlight into chemical energy.",
    },
    {
        "block_id": "p-2",
        "text": "The glucose is then transported - via the phloem - to additional parts of the plant, where it is stored.",
    },
    {
        "block_id": "p-3",
        "text": "Farmers who take a laissez-faire approach to watering may find that their crops are DAMAGED by drought.",
    },
    {
        "block_id": "p-4",
        "text": "Plants need light. Plants need water. Plants also need carbon dioxide from the air.",
    },
]


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------
def to_dict(obj):
    """Pydantic model / list / dict -> plain JSON-able data."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, list):
        return [to_dict(x) for x in obj]
    if isinstance(obj, dict):
        return {k: to_dict(v) for k, v in obj.items()}
    return obj


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def find_html(data):
    """Find the adapted HTML string anywhere inside the AdaptResult dict."""
    if isinstance(data, str):
        low = data.lower()
        return data if ("<html" in low or "<!doctype" in low) else None
    if isinstance(data, dict):
        for v in data.values():
            found = find_html(v)
            if found:
                return found
    if isinstance(data, list):
        for v in data:
            found = find_html(v)
            if found:
                return found
    return None


def find_block_list(data):
    """Find a list of dicts that each have a block_id (the adapted blocks) inside the result."""
    if isinstance(data, list) and data and all(isinstance(x, dict) and "block_id" in x for x in data):
        return data
    if isinstance(data, dict):
        for v in data.values():
            found = find_block_list(v)
            if found:
                return found
    if isinstance(data, list):
        for v in data:
            found = find_block_list(v)
            if found:
                return found
    return None


def show_recs(title: str, recs) -> None:
    print(f"\n=== {title}: {len(recs)} recommendation(s) ===")
    for i, r in enumerate(recs, 1):
        d = to_dict(r)
        # print a short line using whatever common fields exist
        rule = d.get("rule_id") or d.get("guideline_id") or d.get("rule") or "?"
        block = d.get("block_id") or d.get("target") or d.get("selector") or ""
        msg = d.get("message") or d.get("reason") or d.get("description") or d.get("suggestion") or ""
        print(f"  {i:>2}. [{rule}] {block} {str(msg)[:90]}")


def pick_accepted(recs, deny_idx: set[int]):
    """Simulate the user: accept everything except the denied ones."""
    accepted = []
    for i, r in enumerate(recs, 1):
        if i in deny_idx:
            accepted.append(r.model_copy(update={"status": "denied"}))
        else:
            accepted.append(r)  # still "pending": the orchestrator treats it as accepted
    return accepted


# --------------------------------------------------------------------------------------
# Level runners
# --------------------------------------------------------------------------------------
def run_level1(all_recs: dict, deny_idx: set[int]) -> None:
    print("\n" + "#" * 70 + "\n# LEVEL 1 (representation / CSS)\n" + "#" * 70)
    (OUT / "original.html").write_text(SAMPLE_HTML, encoding="utf-8")

    result = analyze(1, html=SAMPLE_HTML)
    recs = result.recommendations
    show_recs("Level 1 analyze", recs)
    all_recs["level1"] = {
        "findings": to_dict(result.findings) if result.findings is not None else None,
        "recommendations": to_dict(recs),
    }

    accepted = pick_accepted(recs, deny_idx)
    adapted = apply(1, html=SAMPLE_HTML, accepted=accepted)
    data = to_dict(adapted)
    write_json(OUT / "adapted_level1.json", data)

    html = find_html(data)
    if html:
        (OUT / "adapted_level1.html").write_text(html, encoding="utf-8")
        print(f"\n  wrote results/adapted_level1.html  (open it next to results/original.html)")
    else:
        print("\n  Could not find an HTML string in the AdaptResult; check results/adapted_level1.json")
    print("  wrote results/adapted_level1.json")


def run_level2(all_recs: dict, deny_idx: set[int]) -> None:
    print("\n" + "#" * 70 + "\n# LEVEL 2 (plain-language text, calls the model)\n" + "#" * 70)

    result = analyze(2, blocks=SAMPLE_BLOCKS)
    recs = result.recommendations
    show_recs("Level 2 analyze", recs)
    all_recs["level2"] = {
        "findings": to_dict(result.findings) if result.findings is not None else None,
        "recommendations": to_dict(recs),
    }

    accepted = pick_accepted(recs, deny_idx)
    adapted = apply(2, blocks=SAMPLE_BLOCKS, accepted=accepted)
    data = to_dict(adapted)
    write_json(OUT / "adapted_level2.json", data)
    print("\n  wrote results/adapted_level2.json")

    # Best-effort before/after text file
    new_blocks = find_block_list(data)
    if new_blocks:
        before = {b["block_id"]: b["text"] for b in SAMPLE_BLOCKS}
        lines = []
        for nb in new_blocks:
            bid = nb["block_id"]
            after = nb.get("text") or nb.get("adapted_text") or nb.get("new_text") or ""
            lines += [f"[{bid}]", f"  BEFORE: {before.get(bid, '')}", f"  AFTER : {after}", ""]
        (OUT / "adapted_level2.txt").write_text("\n".join(lines), encoding="utf-8")
        print("  wrote results/adapted_level2.txt")


# --------------------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--level", type=int, choices=[1, 2], help="run only one level")
    parser.add_argument("--deny", default="", help="comma-separated 1-based recommendation numbers to deny, e.g. 1,3")
    args = parser.parse_args()

    deny_idx = {int(x) for x in args.deny.split(",") if x.strip().isdigit()}
    OUT.mkdir(exist_ok=True)
    all_recs: dict = {}

    levels = [args.level] if args.level else [1, 2]
    for lvl in levels:
        try:
            (run_level1 if lvl == 1 else run_level2)(all_recs, deny_idx)
        except Exception:
            print(f"\n!! Level {lvl} failed:")
            traceback.print_exc()

    write_json(OUT / "recommendations.json", all_recs)
    print("\nwrote results/recommendations.json")
    print("Done. Results are in:", OUT)


if __name__ == "__main__":
    main()