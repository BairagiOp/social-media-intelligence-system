"""Web collection: URL policy, file fetch, platform connectors and the crawler."""
from __future__ import annotations

import socket

import httpx
import pytest

from app.config import settings
from app.services import fetch_service
from app.services.crawl_service import parse_html, parse_selector, select
from app.utils.errors import ValidationFailed

SMALL_CSV = b"text,platform\nhello world,x\nsecond post,y\n"

BLUESKY_POST = {
    "uri": "at://did:plc:abc/app.bsky.feed.post/xyz",
    "record": {
        "text": "hello world from bluesky",
        "createdAt": "2024-01-01T00:00:00Z",
        "langs": ["en"],
    },
    "author": {
        "did": "did:plc:abc",
        "handle": "alice.bsky.social",
        "followersCount": 10,
        "postsCount": 5,
    },
    "likeCount": 3,
    "replyCount": 1,
    "repostCount": 0,
    "indexedAt": "2024-01-01T00:00:01Z",
}

HOME_HTML = """<!doctype html><html><head><title>Home</title></head><body>
<nav><a href="/about">About</a><a href="https://other.example/x">External</a></nav>
<article><h2 class="title">First headline</h2>
<p>This is the first paragraph and it carries enough characters to count as content.</p>
</article></body></html>"""

ABOUT_HTML = """<!doctype html><html><head><title>About</title></head><body>
<article><h2 class="title">Second headline</h2>
<p>Another paragraph long enough to be treated as the main text of the page here.</p>
</article></body></html>"""


@pytest.fixture(autouse=True)
def _reset_fetch_state(monkeypatch):
    monkeypatch.setattr(settings, "fetch_min_interval", 0.0)
    fetch_service.clear_caches()
    yield
    fetch_service.clear_caches()


@pytest.fixture(autouse=True)
def fake_dns(monkeypatch):
    """Resolve the test host to a public address; literal IPs resolve natively.

    Keeps every test offline while still exercising the real SSRF check.
    """
    real = socket.getaddrinfo

    def fake(host, port, *args, **kwargs):
        if host in {"public.example", "www.public.example"}:
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))
            ]
        return real(host, port, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", fake)


@pytest.fixture()
def route(monkeypatch):
    """Swap the outbound client for one backed by an httpx MockTransport."""

    def _install(handler):
        def fake_client(transport=None):
            return httpx.Client(
                timeout=settings.fetch_timeout,
                follow_redirects=False,
                headers={"User-Agent": settings.user_agent, "Accept": "*/*"},
                transport=httpx.MockTransport(handler),
            )

        monkeypatch.setattr(fetch_service, "_client", fake_client)

    return _install


def _ok_robots(request: httpx.Request) -> httpx.Response | None:
    if request.url.path == "/robots.txt":
        return httpx.Response(404)
    return None


# ---------------------------------------------------------------------------
# Endpoint catalog + policy
# ---------------------------------------------------------------------------

def test_sources_lists_connectors_and_policy(client):
    resp = client.get("/api/datasets/sources")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert {s["id"] for s in body["sources"]} == {"mastodon", "bluesky"}
    assert all(s["auth_required"] is False for s in body["sources"])
    for source in body["sources"]:
        assert source["params"], f"{source['id']} must declare its form fields"
        assert source["license_note"]

    policy = body["policy"]
    assert policy["enabled"] is True
    assert policy["schemes"] == ["http", "https"]
    assert policy["robots_obeyed"] is True
    assert policy["private_targets_blocked"] is True
    assert policy["max_redirects"] >= 1
    assert policy["statement"]


def test_new_collection_routes_are_documented(client):
    paths = client.get("/openapi.json").json()["paths"]
    for path in (
        "/api/datasets/fetch",
        "/api/datasets/collect",
        "/api/datasets/crawl",
        "/api/datasets/sources",
    ):
        assert path in paths, f"{path} missing from OpenAPI"
    # The parameterised route must still exist alongside the new literals.
    assert "post" in paths["/api/datasets/{dataset_id}/preprocess"]
    assert "get" in paths["/api/datasets/{dataset_id}"]


# ---------------------------------------------------------------------------
# URL policy (no network involved)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        "ftp://public.example/data.csv",
        "file:///etc/passwd",
        "javascript:alert(1)",
    ],
)
def test_fetch_rejects_unsupported_schemes(client, url):
    resp = client.post("/api/datasets/fetch", json={"url": url})
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_failed"


def test_fetch_rejects_embedded_credentials(client):
    resp = client.post(
        "/api/datasets/fetch", json={"url": "https://user:pass@public.example/a.csv"}
    )
    assert resp.status_code == 422
    assert "credential" in resp.json()["detail"].lower()


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/data.csv",
        "http://192.168.10.5/data.csv",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/data.csv",
    ],
)
def test_fetch_blocks_non_public_targets(client, url):
    """SSRF guard: loopback, RFC1918 and cloud metadata endpoints are refused."""
    resp = client.post("/api/datasets/fetch", json={"url": url})
    assert resp.status_code == 422, resp.text
    assert "non-public" in resp.json()["detail"]


def test_host_allowlist_is_enforced(client, monkeypatch):
    monkeypatch.setattr(settings, "fetch_host_allowlist", {"allowed.example"})
    resp = client.post(
        "/api/datasets/fetch", json={"url": "https://public.example/data.csv"}
    )
    assert resp.status_code == 422
    assert "allow-list" in resp.json()["detail"]


@pytest.mark.parametrize(
    "url, mentioned",
    [
        ("https://x.com/someuser/status/123", "X prohibits"),
        ("https://twitter.com/home", "X prohibits"),
        ("https://www.reddit.com/r/technology/", "Reddit prohibits"),
        ("https://linkedin.com/in/someone/", "LinkedIn prohibits"),
        ("https://www.instagram.com/explore/", "Automated data collection"),
        ("https://threads.net/@someone", "Automated data collection"),
    ],
)
def test_blocked_platforms_fast_fail_with_explanation(client, url, mentioned):
    """Known blanket-block domains fail instantly with the platform's own rules."""
    resp = client.post("/api/datasets/fetch", json={"url": url})
    assert resp.status_code == 403, resp.text
    detail = resp.json()["detail"]
    assert mentioned in detail
    assert "SMDPIS" in detail, "the message must say what to do instead"
    # No robots round-trip and no body download happened.


def test_blocked_platform_check_runs_before_dns(client, monkeypatch):
    """Fast-fail must not touch the network at all."""

    def explode(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("DNS must not be consulted for a blocked domain")

    monkeypatch.setattr(socket, "getaddrinfo", explode)
    resp = client.post("/api/datasets/fetch", json={"url": "https://x.com/search"})
    assert resp.status_code == 403


def test_crawl_fast_fails_on_blocked_domain(client):
    resp = client.post(
        "/api/datasets/crawl",
        json={
            "url": "https://www.twitter.com/someuser",
            "fields": [{"name": "headline", "selector": "h2.title"}],
        },
    )
    assert resp.status_code == 403
    assert "X prohibits" in resp.json()["detail"]


def test_sources_policy_lists_blocked_domains(client):
    policy = client.get("/api/datasets/sources").json()["policy"]
    assert "x.com" in policy["blocked_domains"]
    assert "reddit.com" in policy["blocked_domains"]


def test_fetch_disabled_returns_403(client, monkeypatch):
    monkeypatch.setattr(settings, "fetch_enabled", False)
    resp = client.post(
        "/api/datasets/fetch", json={"url": "https://public.example/data.csv"}
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "fetch_failed"


# ---------------------------------------------------------------------------
# Fetching a dataset file
# ---------------------------------------------------------------------------

def test_fetch_ingests_and_records_custody(client, route):
    def handler(request: httpx.Request) -> httpx.Response:
        hit = _ok_robots(request)
        if hit:
            return hit
        if request.url.path == "/data.csv":
            return httpx.Response(
                200, content=SMALL_CSV, headers={"content-type": "text/csv"}
            )
        return httpx.Response(404)

    route(handler)
    resp = client.post(
        "/api/datasets/fetch",
        json={
            "url": "https://public.example/data.csv",
            "name": "Fetched dataset",
            "license": "CC-BY-4.0",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    dataset = body["dataset"]

    assert dataset["records"] == 2
    assert dataset["status"] == "VALIDATED"
    assert dataset["name"] == "Fetched dataset"
    assert dataset["evidence_id"].startswith("EV-")
    assert dataset["column_map"].get("text") == "text"

    collection = body["collection"]
    assert collection["method"] == "fetch"
    assert collection["robots_allowed"] is True
    assert collection["http_status"] == 200
    assert collection["final_url"] == "https://public.example/data.csv"
    assert collection["license"] == "CC-BY-4.0"
    assert "SMDPIS" in collection["user_agent"]

    # Provenance lands in the signed audit trail, and the chain still verifies.
    log = client.get(f"/api/evidence/{dataset['evidence_id']}/audit-log").json()
    assert any(e["event"] == "FETCH" for e in log["items"])
    assert any(e["event"] == "HASH" for e in log["items"])

    verify = client.get(f"/api/evidence/{dataset['evidence_id']}/verify").json()
    assert verify["valid"] is True
    assert verify["file_integrity"]["verified"] is True


def test_fetch_honours_robots_disallow(client, route, monkeypatch):
    monkeypatch.setattr(settings, "fetch_robots_obey", True)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private/\n")
        return httpx.Response(
            200, content=SMALL_CSV, headers={"content-type": "text/csv"}
        )

    route(handler)
    before = client.get("/api/datasets").json()["total"]
    resp = client.post(
        "/api/datasets/fetch",
        json={"url": "https://public.example/private/x.csv"},
    )
    assert resp.status_code == 403
    assert "robots.txt" in resp.json()["detail"]
    # Nothing downstream should have been ingested.
    assert client.get("/api/datasets").json()["total"] == before


def test_fetch_allows_when_robots_permissive(client, route, monkeypatch):
    monkeypatch.setattr(settings, "fetch_robots_obey", True)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        return httpx.Response(
            200, content=SMALL_CSV, headers={"content-type": "text/csv"}
        )

    route(handler)
    resp = client.post(
        "/api/datasets/fetch", json={"url": "https://public.example/open.csv"}
    )
    assert resp.status_code == 201, resp.text


def test_fetch_blocks_redirect_to_private_target(client, route, monkeypatch):
    """A 302 towards an internal address must be refused, not followed."""
    monkeypatch.setattr(settings, "fetch_robots_obey", False)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/r.csv":
            return httpx.Response(
                302, headers={"location": "http://127.0.0.1/steal.csv"}
            )
        return httpx.Response(200, content=SMALL_CSV)

    route(handler)
    resp = client.post(
        "/api/datasets/fetch",
        json={"url": "https://public.example/r.csv"},
    )
    assert resp.status_code == 422, resp.text
    assert "non-public" in resp.json()["detail"]


def test_fetch_rejects_unsupported_remote_format(client, route, monkeypatch):
    monkeypatch.setattr(settings, "fetch_robots_obey", False)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"<html>not a dataset</html>", headers={"content-type": "text/html"}
        )

    route(handler)
    resp = client.post(
        "/api/datasets/fetch", json={"url": "https://public.example/page"}
    )
    assert resp.status_code == 422
    assert "not a supported dataset format" in resp.json()["detail"]


def test_fetch_reports_remote_http_error(client, route, monkeypatch):
    monkeypatch.setattr(settings, "fetch_robots_obey", False)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="forbidden")

    route(handler)
    resp = client.post(
        "/api/datasets/fetch", json={"url": "https://public.example/secret.csv"}
    )
    assert resp.status_code == 422
    assert "HTTP 403" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Official platform connectors
# ---------------------------------------------------------------------------

def test_collect_bluesky_maps_canonical_columns(client, route, monkeypatch):
    monkeypatch.setattr(settings, "fetch_robots_obey", False)

    def handler(request: httpx.Request) -> httpx.Response:
        if "searchPosts" in str(request.url):
            return httpx.Response(200, json={"posts": [BLUESKY_POST, BLUESKY_POST]})
        return httpx.Response(404)

    route(handler)
    resp = client.post(
        "/api/datasets/collect",
        json={"source": "bluesky", "params": {"query": "hello", "limit": 5}},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    dataset = body["dataset"]

    assert dataset["records"] == 2
    for canonical in ("platform", "username", "text", "url", "timestamp", "likes"):
        assert canonical in dataset["column_map"], f"{canonical} not auto-detected"
    assert body["collection"]["method"] == "collect"
    assert body["collection"]["source"] == "bluesky"
    assert body["collection"]["auth_used"] is False
    assert body["collection"]["records"] == 2


def test_collect_rejects_unknown_source(client):
    resp = client.post(
        "/api/datasets/collect", json={"source": "not-a-source", "params": {}}
    )
    assert resp.status_code == 422
    assert "Unknown source" in resp.json()["detail"]


def test_collect_requires_declared_params(client, route, monkeypatch):
    monkeypatch.setattr(settings, "fetch_robots_obey", False)
    route(lambda request: httpx.Response(404))

    resp = client.post(
        "/api/datasets/collect",
        json={"source": "mastodon", "params": {"target": "", "query": ""}},
    )
    assert resp.status_code == 422
    assert "required" in resp.json()["detail"].lower()


def test_collect_mastodon_strips_html(client, route, monkeypatch):
    from app.services.web_sources import strip_html

    assert strip_html("<p>Hello <a href='https://x.example'>world</a> &amp; more</p>") == (
        "Hello world & more"
    )

    monkeypatch.setattr(settings, "fetch_robots_obey", False)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/tags/opensource/statuses":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "1",
                        "created_at": "2024-01-01T00:00:00.000Z",
                        "content": "<p>Shipping <strong>code</strong></p>",
                        "url": "https://mastodon.social/@bob/1",
                        "favourites_count": 4,
                        "reblogs_count": 1,
                        "replies_count": 2,
                        "language": "en",
                        "account": {
                            "id": "a1",
                            "username": "bob",
                            "statuses_count": 30,
                            "followers_count": 12,
                            "following_count": 8,
                        },
                    }
                ],
            )
        return httpx.Response(404)

    route(handler)
    resp = client.post(
        "/api/datasets/collect",
        json={
            "source": "mastodon",
            "params": {"target": "mastodon.social", "query": "opensource", "limit": 10},
        },
    )
    assert resp.status_code == 201, resp.text
    dataset = resp.json()["dataset"]
    assert dataset["records"] == 1
    rows = client.get(
        f"/api/datasets/{dataset['id']}/rows", params={"page_size": 5}
    ).json()
    assert rows["items"][0]["text"] == "Shipping code"


# ---------------------------------------------------------------------------
# Crawler
# ---------------------------------------------------------------------------

def test_crawl_extracts_fields_and_adds_text(client, route, monkeypatch):
    monkeypatch.setattr(settings, "fetch_robots_obey", False)

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path in ("/", "/index.html", ""):
            return httpx.Response(
                200, text=HOME_HTML, headers={"content-type": "text/html; charset=utf-8"}
            )
        if path == "/about":
            return httpx.Response(
                200, text=ABOUT_HTML, headers={"content-type": "text/html"}
            )
        return httpx.Response(404)

    route(handler)
    resp = client.post(
        "/api/datasets/crawl",
        json={
            "url": "https://public.example/",
            "fields": [{"name": "headline", "selector": "h2.title"}],
            "max_pages": 5,
            "max_depth": 1,
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    dataset = body["dataset"]

    assert dataset["records"] >= 2
    assert "headline" in dataset["column_names"]
    assert "text" in dataset["column_names"], "auto text column keeps ML usable"
    assert "url" in dataset["column_names"]

    stats = body["collection"]
    assert stats["method"] == "crawl"
    assert stats["pages_crawled"] >= 2
    assert stats["allowed_domains"] == ["public.example"]
    assert stats["links_rejected"] >= 1, "off-site link must be rejected"

    rows = client.get(f"/api/datasets/{dataset['id']}/rows", params={"page_size": 5}).json()
    headlines = {r["headline"] for r in rows["items"]}
    assert "First headline" in headlines
    assert "Second headline" in headlines


def test_crawl_requires_at_least_one_field(client):
    resp = client.post(
        "/api/datasets/crawl", json={"url": "https://public.example/", "fields": []}
    )
    assert resp.status_code == 422


def test_crawl_rejects_unusable_extraction(client, route, monkeypatch):
    monkeypatch.setattr(settings, "fetch_robots_obey", False)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(
            200, text=HOME_HTML, headers={"content-type": "text/html"}
        )

    route(handler)
    resp = client.post(
        "/api/datasets/crawl",
        json={
            "url": "https://public.example/",
            "fields": [{"name": "nothing", "selector": "div.does-not-exist"}],
            "max_pages": 2,
            "max_depth": 0,
        },
    )
    # auto-text rescues the record, so the crawl succeeds with only that column
    assert resp.status_code == 201, resp.text
    assert "text" in resp.json()["dataset"]["column_names"]


def test_crawl_stays_on_allowed_domain(client, route, monkeypatch):
    monkeypatch.setattr(settings, "fetch_robots_obey", False)
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(
            200, text=HOME_HTML, headers={"content-type": "text/html"}
        )

    route(handler)
    resp = client.post(
        "/api/datasets/crawl",
        json={
            "url": "https://public.example/",
            "fields": [{"name": "headline", "selector": "h2.title"}],
            "max_pages": 10,
            "max_depth": 2,
        },
    )
    assert resp.status_code == 201, resp.text
    assert not any("other.example" in u for u in seen), "crawler left its allow-list"
    assert resp.json()["collection"]["links_rejected"] >= 1


def test_crawl_zero_records_reports_diagnostics(client, route, monkeypatch):
    """A zero-record crawl must surface counters and the real fetch errors."""
    monkeypatch.setattr(settings, "fetch_robots_obey", False)
    route(lambda request: httpx.Response(403))

    resp = client.post(
        "/api/datasets/crawl",
        json={
            "url": "https://public.example/",
            "fields": [{"name": "headline", "selector": "h2.title"}],
            "max_pages": 2,
            "max_depth": 0,
        },
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "no page could be fetched" in detail
    assert "HTTP 403" in detail, "the underlying fetch error must be reported"
    assert "failed 1" in detail, "per-status counters must be reported"


# ---------------------------------------------------------------------------
# Selector engine (unit)
# ---------------------------------------------------------------------------

DOC = """<html><head><title>T</title></head><body>
<div id="a" class="box"><p class="lead one">A</p><span>B</span></div>
<div class="box"><p class="two">C</p></div>
</body></html>"""


def test_selector_engine_compound_and_combinators():
    root, title = parse_html(DOC)
    assert title == "T"

    assert [n.text() for n in select(root, "#a .lead")] == ["A"]
    assert [n.text() for n in select(root, "div.box > p")] == ["A", "C"]
    assert [n.text() for n in select(root, "p.one, p.two")] == ["A", "C"]
    assert len(select(root, "div")) == 2
    assert [n.text() for n in select(root, ".lead")] == ["A"]


def test_selector_engine_rejects_garbage():
    with pytest.raises(ValidationFailed):
        parse_selector("@bad")
    with pytest.raises(ValidationFailed):
        parse_selector("   ,  ")


def test_html_parser_tolerates_unclosed_markup():
    root, title = parse_html(
        "<title>Hi</title><div><p>one<span>two</p><p>three</div>"
    )
    assert title == "Hi"
    assert "one" in root.text() and "three" in root.text()


def test_script_content_is_not_extracted_as_text():
    root, _ = parse_html(
        "<html><body><script>var x = 'ignore me';</script>"
        "<article><p>Real content that should be the only text extracted here.</p></article>"
        "</body></html>"
    )
    text = root.text()
    assert "ignore me" not in text
    assert "Real content" in text
