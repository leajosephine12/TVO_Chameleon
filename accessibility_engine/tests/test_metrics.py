"""One fixture with planted violations; every browserless metric must fire exactly where planted."""
from accessibility_metrics import THRESHOLDS, analyze_text, structure_checks

LONG_SENTENCE = (
    "In order to successfully complete the registration procedure, students are required to "
    "navigate to the enrollment section, locate the appropriate course offering, and subsequently "
    "confirm their selection before the deadline elapses or the window closes."
)

HTML = f"""
<html><body>
<nav><ul>
  <li><a href="/a">Topics</a>
    <ul><li><a href="/b">Deep</a>
      <ul><li><a href="/c">Deeper</a></li></ul>
    </li></ul>
  </li>
</ul></nav>
<nav><a href="/other">Second nav</a></nav>
<section>
  <p>{LONG_SENTENCE} The form was submitted by the students. NASA built it.</p>
  <p>{"Short words fill this long paragraph. " * 12}</p>
</section>
<ul>{"".join(f"<li>Item {i}</li>" for i in range(9))}</ul>
<ul><li>First sentence here. Second sentence too.</li></ul>
<a href="/x">click here</a>
<button><img src="gear.png" alt=""></button>
<img src="photos/sunset.png" alt="sunset">
<p><img src="star.svg"></p>
<button>Submit</button>
<video autoplay src="v.mp4"></video>
<div class="carousel">{"".join(f"<div>slide {i}</div>" for i in range(7))}</div>
</body></html>
"""


def blocks_from(html):  # minimal stand-in for the backend's block extraction
    from bs4 import BeautifulSoup
    from collections import Counter
    soup, counts, out = BeautifulSoup(html, "html.parser"), Counter(), []
    for tag in soup.find_all(True):
        counts[tag.name] += 1
        if tag.name == "p" and tag.get_text(strip=True):
            out.append({"block_id": f"{tag.name}-{counts[tag.name]}", "text": tag.get_text(), "kind": "p"})
    return out


def test_text_metrics():
    found = {f["metric_id"]: f for f in analyze_text(blocks_from(HTML))["findings"]}
    assert found["T3"]["measured"]["word_count"] > 25        # long sentence
    assert found["T4"]["measured"]["conjunctions"] > 2       # chained conjunctions
    assert found["T6"].get("report_only") is True            # passive voice, report-only
    assert found["T1"]["measured"]["flesch_kincaid_grade"] > 6
    assert "S1" in found                                     # long paragraph
    assert "nasa" not in found.get("T7", {}).get("measured", {}).get("rare_words", [])  # proper noun excluded


def test_structure_checks():
    found = {f["metric_id"] for f in structure_checks(HTML, url="https://tvo.org/a/b/c/d")["findings"]}
    assert {"S2", "S3", "S5", "T8", "J5", "J11", "J12", "J14", "N1", "N2", "N6", "N8", "L11", "M1", "M2"} <= found


def test_findings_carry_citations():
    for f in structure_checks(HTML)["findings"] + analyze_text(blocks_from(HTML))["findings"]:
        assert f["metric_id"] in THRESHOLDS
        assert f["threshold"] and f["source"] and f["tier"] in "CDEF"


def test_clean_page_is_quiet():
    clean = """<html><body>
      <nav><a href="/" aria-current="page">Home</a><a href="/about">About us</a></nav>
      <input type="search" name="search">
      <section><h2>Our garden</h2><p>We grow beans. The beans grow fast. Kids water them each day.</p></section>
    </body></html>"""
    assert structure_checks(clean)["findings"] == []
    blocks = [{"block_id": "p-1", "text": "We grow beans. The beans grow fast.", "kind": "p"}]
    assert analyze_text(blocks)["findings"] == []
