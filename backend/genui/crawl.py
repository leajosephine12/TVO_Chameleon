"""Bounded same-origin page discovery and measurements for the crawl metrics."""

from __future__ import annotations

import http.client
import ipaddress
import re
import socket
import ssl
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup, Tag

from accessibility_metrics.thresholds import finding

MAX_CRAWL_PAGES = 6
CRAWL_TIMEOUT_SECONDS = 5
MAX_CRAWL_RESPONSE_BYTES = 1_000_000
# Only these crawl-bucket metrics have a defined measurement or safe action here.
CRAWL_METRICS = ("J7", "J8", "N4")
_SKIP_EXTENSIONS = {
    ".7z", ".avi", ".css", ".csv", ".doc", ".docx", ".gif", ".gz", ".ico", ".jpeg", ".jpg",
    ".js", ".json", ".mp3", ".mp4", ".pdf", ".png", ".ppt", ".pptx", ".svg", ".tar", ".webp",
    ".xls", ".xlsx", ".xml", ".zip",
}
_WHITESPACE = re.compile(r"\s+")


class CrawlFetchError(Exception):
    """A page could not be fetched under the crawl's network and size limits."""


@dataclass(frozen=True)
class CrawledPage:
    url: str
    html: str


@dataclass(frozen=True)
class CrawlSnapshot:
    seed_url: str
    pages: tuple[CrawledPage, ...]
    warnings: tuple[dict[str, str], ...] = ()

    @property
    def websites(self) -> list[str]:
        return sorted({f"{urlsplit(page.url).scheme}://{urlsplit(page.url).netloc}" for page in self.pages})

    def report(self) -> dict:
        return {
            "enabled": True,
            "seed_url": _display_url(self.seed_url),
            "page_count": len(self.pages),
            "pages": [_display_url(page.url) for page in self.pages],
            "websites": self.websites,
            "metrics": list(CRAWL_METRICS),
            "warnings": [{**warning, "url": _display_url(warning["url"])} for warning in self.warnings],
        }


def _origin(url: str) -> tuple[str, str, int]:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        raise ValueError("crawl requires an absolute HTTP(S) URL without embedded credentials.")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as exc:
        raise ValueError("crawl URL has an invalid port.") from exc
    raw_host = parts.hostname.rstrip(".")
    try:
        host = ipaddress.ip_address(raw_host).compressed
    except ValueError:
        host = raw_host.encode("idna").decode("ascii").lower()
    return parts.scheme.lower(), host, port


def _canonical_url(url: str) -> str:
    parts = urlsplit(url)
    scheme, host, port = _origin(url)
    default_port = 443 if scheme == "https" else 80
    formatted_host = f"[{host}]" if ":" in host else host
    netloc = formatted_host if port == default_port else f"{formatted_host}:{port}"
    return urlunsplit((scheme, netloc, parts.path or "/", parts.query, ""))


def _display_url(url: str) -> str:
    parts = urlsplit(url)
    query = "query=REDACTED" if parts.query else ""
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", query, ""))


def _same_origin_url(candidate: str, seed_url: str) -> str | None:
    try:
        if _origin(candidate) != _origin(seed_url):
            return None
        canonical = _canonical_url(candidate)
    except (UnicodeError, ValueError):
        return None
    path = urlsplit(canonical).path.lower()
    if any(path.endswith(extension) for extension in _SKIP_EXTENSIONS):
        return None
    return canonical


def _label(anchor: Tag) -> str:
    return _WHITESPACE.sub(" ", anchor.get_text(" ", strip=True)).strip()


def _page_links(html: str, page_url: str, seed_url: str) -> list[tuple[str, str]]:
    links = _page_link_entries(html, page_url, seed_url)
    unique: list[tuple[str, str]] = []
    seen: set[str] = set()
    for label, target in links:
        if target not in seen:
            unique.append((label, target))
            seen.add(target)
    return unique


def _resolve_internal(page_url: str, href: str, seed_url: str) -> str | None:
    try:
        return _same_origin_url(urljoin(page_url, href), seed_url)
    except ValueError:
        return None


def _page_link_entries(html: str, page_url: str, seed_url: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    links: list[tuple[str, str]] = []
    for anchor in soup.find_all("a", href=True):
        label = _label(anchor)
        if not label:
            continue
        target = _resolve_internal(page_url, anchor["href"].strip(), seed_url)
        if target:
            links.append((label, target))
    return links


def _resolved_public_address(host: str, port: int) -> tuple[int, int, int, str, tuple]:
    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise CrawlFetchError("host lookup failed.") from exc
    if not addresses:
        raise CrawlFetchError("host did not resolve to an address.")
    for address in addresses:
        try:
            public = ipaddress.ip_address(address[4][0]).is_global
        except ValueError as exc:
            raise CrawlFetchError("host resolved to an invalid address.") from exc
        if not public:
            raise CrawlFetchError("host resolved to a non-public address.")
    return addresses[0]


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host: str, port: int, address: tuple[int, int, int, str, tuple], timeout: float):
        super().__init__(host, port, timeout=timeout)
        self._address = address

    def connect(self):
        family, socktype, proto, _, sockaddr = self._address
        sock = socket.socket(family, socktype, proto)
        sock.settimeout(self.timeout)
        try:
            sock.connect(sockaddr)
        except (OSError, ssl.SSLError, http.client.HTTPException):
            sock.close()
            raise
        self.sock = sock


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, port: int, address: tuple[int, int, int, str, tuple], timeout: float):
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self._address = address

    def connect(self):
        family, socktype, proto, _, sockaddr = self._address
        raw = socket.socket(family, socktype, proto)
        raw.settimeout(self.timeout)
        try:
            raw.connect(sockaddr)
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except (OSError, ssl.SSLError, http.client.HTTPException):
            raw.close()
            raise


def _fetch_html(url: str) -> str:
    deadline = time.monotonic() + CRAWL_TIMEOUT_SECONDS
    parts = urlsplit(url)
    scheme, host, port = _origin(url)
    address = _resolved_public_address(host, port)
    connection_type = _PinnedHTTPSConnection if scheme == "https" else _PinnedHTTPConnection
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise CrawlFetchError("page request exceeded the five-second time limit.")
    connection = connection_type(host, port, address, remaining)
    target = urlunsplit(("", "", parts.path or "/", parts.query, ""))
    try:
        connection.request(
            "GET",
            target,
            headers={"Accept": "text/html", "Accept-Encoding": "identity", "User-Agent": "TVO-Chameleon-GenUI/1.0"},
        )
        remaining = deadline - time.monotonic()
        if remaining <= 0 or connection.sock is None:
            raise CrawlFetchError("page request exceeded the five-second time limit.")
        connection.sock.settimeout(remaining)
        response = connection.getresponse()
        if response.status != 200:
            raise CrawlFetchError(f"server returned HTTP {response.status}; redirects are not followed.")
        if response.headers.get_content_type().lower() != "text/html":
            raise CrawlFetchError("response is not an HTML page.")
        if response.headers.get("Content-Encoding", "identity").lower() not in {"", "identity"}:
            raise CrawlFetchError("compressed responses are not accepted.")
        chunks = []
        size = 0
        while size <= MAX_CRAWL_RESPONSE_BYTES:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CrawlFetchError("page request exceeded the five-second time limit.")
            if connection.sock is None:
                raise CrawlFetchError("page connection closed before the response was complete.")
            connection.sock.settimeout(remaining)
            chunk = response.read1(min(65_536, MAX_CRAWL_RESPONSE_BYTES + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
        if size > MAX_CRAWL_RESPONSE_BYTES:
            raise CrawlFetchError("response exceeded the 1 MB page limit.")
        body = b"".join(chunks)
        charset = response.headers.get_content_charset() or "utf-8"
        try:
            return body.decode(charset, errors="replace")
        except LookupError:
            return body.decode("utf-8", errors="replace")
    except CrawlFetchError:
        raise
    except (OSError, ssl.SSLError, http.client.HTTPException, UnicodeError) as exc:
        raise CrawlFetchError(f"page request failed ({type(exc).__name__}).") from exc
    finally:
        connection.close()


def crawl_unit(
    seed_url: str,
    seed_html: str,
    *,
    fetcher: Callable[[str], str] = _fetch_html,
    max_pages: int = MAX_CRAWL_PAGES,
) -> CrawlSnapshot:
    """Fetch a bounded sample of direct same-origin links from the page being analyzed."""
    if max_pages < 1 or max_pages > MAX_CRAWL_PAGES:
        raise ValueError(f"max_pages must be between 1 and {MAX_CRAWL_PAGES}.")
    seed_url = _canonical_url(seed_url)
    pages = [CrawledPage(seed_url, seed_html)]
    warnings: list[dict[str, str]] = []
    candidates = _page_links(seed_html, seed_url, seed_url)
    attempts = 1
    for _, target in candidates:
        if target == seed_url:
            continue
        if attempts >= max_pages:
            break
        attempts += 1
        try:
            html = fetcher(target)
        except CrawlFetchError as exc:
            warnings.append({"url": target, "reason": str(exc)})
            continue
        pages.append(CrawledPage(target, html))
    snapshot = CrawlSnapshot(seed_url, tuple(pages), tuple(warnings))
    return snapshot


def _page_title(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    heading = soup.find("h1")
    return _WHITESPACE.sub(" ", title or (heading.get_text(" ", strip=True) if heading else "")).strip()


def _nav_order(html: str, page_url: str, seed_url: str) -> tuple[str, ...]:
    soup = BeautifulSoup(html, "html.parser")
    for nav in soup.find_all("nav"):
        order = []
        for anchor in nav.find_all("a", href=True):
            target = _resolve_internal(page_url, anchor["href"].strip(), seed_url)
            if target:
                order.append(target)
        if order:
            return tuple(order)
    return ()


def _order_differs(first: tuple[str, ...], other: tuple[str, ...]) -> bool:
    common = set(first) & set(other)
    return len(common) > 1 and [url for url in first if url in common] != [url for url in other if url in common]


def measure_crawl(snapshot: CrawlSnapshot, *, seed_html: str | None = None) -> list[dict]:
    """Measure only the crawl metrics with a defined calculation; unsupported metrics stay excluded."""
    pages = list(snapshot.pages)
    if seed_html is not None:
        pages = [
            CrawledPage(page.url, seed_html) if page.url == snapshot.seed_url else page
            for page in pages
        ]
    page_data = []
    for page in pages:
        page_data.append({
            "url": page.url,
            "title": _page_title(page.html),
            "links": _page_link_entries(page.html, page.url, snapshot.seed_url),
            "nav_order": _nav_order(page.html, page.url, snapshot.seed_url),
        })

    label_groups: dict[str, list[dict]] = {}
    target_groups: dict[str, list[dict]] = {}
    for page in page_data:
        for label, target in page["links"]:
            entry = {"page": page["url"], "label": label, "target": target}
            label_groups.setdefault(_WHITESPACE.sub(" ", label).strip().casefold(), []).append(entry)
            target_groups.setdefault(target, []).append(entry)

    findings: list[dict] = []
    seed_page = page_data[0]
    for label, target, block_id in _seed_anchor_blocks(pages[0].html, snapshot.seed_url, snapshot.seed_url):
        group = label_groups.get(_WHITESPACE.sub(" ", label).strip().casefold(), [])
        targets = sorted({entry["target"] for entry in group})
        if len(targets) > 1:
            details = [
                {"label": entry["label"], "target": _display_url(entry["target"]), "page": _display_url(entry["page"]),
                 "title": next((p["title"] for p in page_data if p["url"] == entry["target"]), "")}
                for entry in group
            ]
            f = finding(
                "J7",
                block_id,
                {
                    "label": label,
                    "current_target": _display_url(target),
                    "destination_title": next((p["title"] for p in page_data if p["url"] == target), ""),
                    "targets": details,
                    "target_count": len(targets),
                },
                f"The link label {label!r} points to {len(targets)} different destinations in the crawled pages.",
            )
            f["crawl"] = {"pages": sorted({_display_url(entry["page"]) for entry in group}), "websites": snapshot.websites}
            findings.append(f)

        group = target_groups.get(target, [])
        distinct_entries = list({(entry["page"], entry["label"]): entry for entry in group}.values())
        labels = sorted({entry["label"] for entry in distinct_entries}, key=str.casefold)
        source_pages = {entry["page"] for entry in distinct_entries}
        counts = Counter(entry["label"] for entry in distinct_entries)
        most_common = [label for label, count in counts.items() if count == max(counts.values(), default=0)]
        if len(labels) > 1 and len(source_pages) > 1 and len(most_common) == 1 and label != most_common[0]:
            details = [
                {"label": entry["label"], "page": _display_url(entry["page"])}
                for entry in distinct_entries
            ]
            f = finding(
                "J8",
                block_id,
                {"target": _display_url(target), "labels": details, "label_count": len(labels)},
                f"The same destination is called by {len(labels)} different link labels across crawled pages.",
            )
            f["crawl"] = {"pages": sorted({_display_url(url) for url in source_pages}), "websites": snapshot.websites}
            findings.append(f)

    nav_differences = [
        {"url": _display_url(page["url"]), "order": [_display_url(url) for url in page["nav_order"]]}
        for page in page_data[1:]
        if _order_differs(seed_page["nav_order"], page["nav_order"])
    ]
    if nav_differences:
        f = finding(
            "N4",
            "page",
            {
                "pages_compared": len(page_data),
                "different_pages": [item["url"] for item in nav_differences],
                "seed_order": [_display_url(url) for url in seed_page["nav_order"]],
                "other_orders": nav_differences,
            },
            f"Navigation order differs from the analyzed page on {len(nav_differences)} of {max(len(page_data) - 1, 0)} sampled pages.",
        )
        f["report_only"] = True
        f["crawl"] = {"pages": [_display_url(snapshot.seed_url), *(item["url"] for item in nav_differences)],
                      "websites": snapshot.websites}
        findings.append(f)
    return findings


def _seed_anchor_blocks(html: str, page_url: str, seed_url: str) -> list[tuple[str, str, str]]:
    from app.adaptation_engine import _index_blocks
    from app.model.adapted_renderer import block_text

    soup = BeautifulSoup(html, "html.parser")
    index = _index_blocks(soup)
    ids = {id(tag): block_id for block_id, tag in index.items()}
    anchors = []
    for anchor in soup.find_all("a", href=True):
        label = block_text(anchor)
        target = _resolve_internal(page_url, anchor["href"].strip(), seed_url)
        if label and target and id(anchor) in ids:
            anchors.append((_WHITESPACE.sub(" ", label).strip(), target, ids[id(anchor)]))
    return anchors
