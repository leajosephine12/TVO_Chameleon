# run: uv run python tests/test_main_updated.py   (or: uv run pytest test_main.py -s)
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # backend/

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

HTML = """<!doctype html><html><head><title>Photosynthesis</title>
<style>body{font-family:"Times New Roman",serif;font-size:12px;background:#fff;color:#000}</style></head>
<body><h1>How plants make food</h1>
<p>Photosynthesis is utilised by plants in order to facilitate the conversion of sunlight into chemical energy.</p>
<p>Farmers who take a laissez-faire approach to watering may find that their crops are DAMAGED by drought.</p>
<p style="font-style:italic">Plants need light, water and carbon dioxide.</p>
</body></html>"""


def run_level(level: int, deny: set[int] = frozenset()):
    r = client.post("/analyze", json={"html": HTML, "level": level})
    assert r.status_code == 200, r.text
    body = r.json()
    recs = body["recommendations"]
    print(f"\nLEVEL {level}: {len(recs)} recs, model_error={body['model_error']}")
    for i, rec in enumerate(recs, 1):
        print(f"  {i}. {rec.get('type')} {rec.get('block_id')} status={rec.get('status')}")

    # simulate the user: deny some, accept the rest
    for i, rec in enumerate(recs, 1):
        rec["status"] = "denied" if i in deny else "accepted"

    r = client.post("/adapted", json={"html": HTML, "level": level, "recommendations": recs})
    assert r.status_code == 200, r.text
    out = r.json()
    print("  applied:", out["applied"], "| skipped:", out["skipped"])
    assert out["adapted_html"] != HTML, "nothing changed"
    open(f"adapted_level{level}.html", "w", encoding="utf-8").write(out["adapted_html"])
    return recs, out


def test_level1():
    recs, out = run_level(1)
    assert recs and "<style" in out["adapted_html"]


def test_level1_denied_stays_denied():
    recs, out = run_level(1, deny={1})
    assert recs[0]["id"] not in out["applied"]


def test_level2():  # needs .env / model
    recs, out = run_level(2)
    assert recs


def test_bad_level():
    assert client.post("/analyze", json={"html": HTML, "level": 3}).status_code == 422


def test_empty_html():
    assert client.post("/analyze", json={"html": "", "level": 1}).status_code == 422


if __name__ == "__main__":
    test_level1(); test_level1_denied_stays_denied(); test_bad_level(); test_empty_html(); test_level2()
    print("\nall passed")