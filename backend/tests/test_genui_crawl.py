import socket
from collections import Counter

import pytest

from genui.crawl import MAX_CRAWL_PAGES, CrawlFetchError, _fetch_html, crawl_unit, measure_crawl


SEED_URL = "https://school.example/unit"
SEED_HTML = """<html><head><title>Unit</title></head><body>
<nav><a href="/first">Open the lesson</a><a href="/second">Open the lesson</a></nav>
<main><a href="/shared">Guide</a></main>
</body></html>"""
PAGES = {
    "https://school.example/first": """<html><head><title>First destination</title></head><body>
<nav><a href="/second">Second</a><a href="/first">First</a></nav>
<a href="/shared">Shared guide</a><a href="/other">Open the lesson</a>
</body></html>""",
    "https://school.example/second": """<html><head><title>Second destination</title></head><body>
<nav><a href="/first">First</a><a href="/second">Second</a></nav>
<a href="/shared">Shared guide</a>
</body></html>""",
    "https://school.example/shared": "<html><title>Shared destination</title></html>",
}


def _snapshot():
    def fetch(url):
        return PAGES[url]

    return crawl_unit(SEED_URL, SEED_HTML, fetcher=fetch)


def test_crawl_selects_only_unique_direct_same_origin_html_pages_and_obeys_page_cap():
    html = """<a href="/one">One</a><a href="/one#top">Same page</a>
    <a href="https://elsewhere.example/two">External</a><a href="/file.pdf">PDF</a>
    <a href="/three">Three</a>"""
    fetched = []

    snapshot = crawl_unit(
        SEED_URL,
        html,
        max_pages=2,
        fetcher=lambda url: fetched.append(url) or "<title>Fetched</title>",
    )

    assert fetched == ["https://school.example/one"]
    assert snapshot.report()["pages"] == [SEED_URL, "https://school.example/one"]
    assert snapshot.report()["websites"] == ["https://school.example"]

    fetched.clear()
    crawl_unit(
        SEED_URL,
        html,
        fetcher=lambda url: fetched.append(url) or "<title>Fetched</title>",
    )
    assert fetched == ["https://school.example/one", "https://school.example/three"]


def test_failed_fetches_still_consume_the_request_budget():
    html = "".join(f'<a href="/page-{number}">Page {number}</a>' for number in range(10))
    fetched = []

    def fail(url):
        fetched.append(url)
        raise CrawlFetchError("unavailable.")

    snapshot = crawl_unit(SEED_URL, html, max_pages=3, fetcher=fail)

    assert len(fetched) == 2
    assert len(snapshot.warnings) == 2


def test_crawl_page_budget_cannot_be_raised_above_the_policy_cap():
    with pytest.raises(ValueError, match="max_pages"):
        crawl_unit(SEED_URL, SEED_HTML, max_pages=MAX_CRAWL_PAGES + 1)


def test_failed_fetches_are_reported_without_discarding_successful_pages():
    def fetch(url):
        if url.endswith("/first"):
            raise CrawlFetchError("host resolved to a non-public address.")
        return PAGES[url]

    snapshot = crawl_unit(SEED_URL, SEED_HTML, fetcher=fetch)

    assert len(snapshot.pages) == 3
    assert snapshot.report()["warnings"] == [
        {"url": "https://school.example/first", "reason": "host resolved to a non-public address."}
    ]


def test_fetch_rejects_non_public_resolved_addresses_before_connecting(monkeypatch):
    private = (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", 80))
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [private])

    with pytest.raises(CrawlFetchError, match="non-public"):
        _fetch_html("http://school.example/private")


def test_only_crawl_metrics_are_measured_and_n4_is_report_only():
    findings = measure_crawl(_snapshot())
    metrics = {finding["metric_id"] for finding in findings}

    assert metrics == {"J7", "J8", "N4"}
    assert all(finding.get("crawl", {}).get("websites") == ["https://school.example"] for finding in findings)
    assert next(f for f in findings if f["metric_id"] == "N4")["report_only"] is True
    assert Counter(f["metric_id"] for f in findings)["J7"] == 2
    assert any(f["metric_id"] == "J8" and f["block_id"] == "a-3" for f in findings)


def test_crawl_recommendations_use_guardrails_and_remeasure_against_crawl_snapshot(monkeypatch):
    from genui import analyze_general, apply_general
    from genui.standin import standin_caller

    monkeypatch.setenv("MODEL_MOCK", "1")
    snapshot = _snapshot()
    monkeypatch.setattr("genui.service.crawl_unit", lambda url, html: snapshot)
    prompts = []

    def capture_prompt(messages, **kwargs):
        prompts.append(messages)
        return standin_caller(messages, **kwargs)

    monkeypatch.setattr("genui.planner.standin_caller", capture_prompt)

    result = analyze_general(SEED_HTML, SEED_URL, crawl=True, judgement=False)
    recommendations = result["recommendations"]

    assert result["crawl"]["enabled"] is True
    assert result["crawl"]["websites"] == ["https://school.example"]
    assert {rec.type for rec in recommendations} == {"J7", "J8"}
    assert all(rec.evidence_type == "crawl" for rec in recommendations)
    assert all(rec.evidence_websites == ["https://school.example"] for rec in recommendations)
    assert all("Websites used: https://school.example" in rec.evidence for rec in recommendations)
    assert all(rec.change["action"] == "set_link_text" for rec in recommendations)
    assert '"crawl":' in prompts[0][1]["content"]
    assert "First destination" in prompts[0][1]["content"]

    accepted = [rec.model_copy(update={"status": "accepted"}) for rec in recommendations]
    adapted = apply_general(SEED_HTML, accepted)
    assert len(adapted["applied"]) == len(recommendations)
    assert adapted["skipped"] == []
    assert "First destination" in adapted["adapted_html"] or "Second destination" in adapted["adapted_html"]
    assert "Shared guide" in adapted["adapted_html"]


def test_crawl_is_opt_in_and_requires_an_absolute_seed_url():
    from genui import analyze_general

    with pytest.raises(ValueError, match="crawl=True requires"):
        analyze_general(SEED_HTML, crawl=True)
