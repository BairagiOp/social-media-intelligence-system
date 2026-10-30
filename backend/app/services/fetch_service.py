"""SSRF-safe outbound HTTP fetching.

Every URL that leaves this process passes `validate_url()`:

* ``http`` / ``https`` only, no embedded credentials,
* the hostname must resolve **only** to public addresses (blocks RFC1918,
  loopback, link-local, multicast, reserved, unspecified) — re-checked after
  *every* redirect hop,
* optional host allow-list from ``SMDPIS_FETCH_HOST_ALLOWLIST``,
* byte cap, timeout and per-host minimum interval,
* ``robots.txt`` honoured unless ``SMDPIS_ROBOTS_OBEY=false``,
* blanket-blocked platforms (X, Reddit, LinkedIn, Meta) fast-fail with an
  explanation of that platform's own published rules — checked **before**
  DNS, so no request (not even ``robots.txt``) is made.

Redirects are followed manually precisely so the guard can run on each hop;
a 302 to ``http://169.254.169.254/`` is rejected, not followed.
"""
from __future__ import annotations

import ipaddress
import logging
import socket
import time
import urllib.robotparser
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import httpx

from app.config import settings
from app.utils.errors import FetchFailed, ValidationFailed

logger = logging.getLogger(__name__)

ALLOWED_SCHEMES = {"http", "https"}
_ROBOTS_TTL_SECONDS = 300.0

# ---------------------------------------------------------------------------
# Blanket-blocked platforms (verified against each site's live robots.txt)
# ---------------------------------------------------------------------------
# These hosts publish a blanket prohibition on automated access AND reject
# non-browser clients beyond robots.txt (connection resets, challenges,
# login walls, JS-only rendering). No configuration makes a fetch succeed,
# so we fail fast with the platform's own stated rules instead of doing a
# doomed round-trip. Not bypassable via SMDPIS_ROBOTS_OBEY — this list is
# about the platform's prohibition and technical futility, not politeness.

_X_REASON = (
    "X prohibits all automated access: its robots.txt publishes "
    "'User-agent: * / Disallow: /', non-browser clients are rejected at "
    "connection level, and post content only exists after JavaScript runs in "
    "a logged-in session. Working around this is outside what SMDPIS will do. "
    "For your own data use X's archive export (Settings > Your account > "
    "Download an archive); for public posts use the Bluesky or Mastodon "
    "connectors."
)
_REDDIT_REASON = (
    "Reddit prohibits automated access: its robots.txt publishes "
    "'User-agent: * / Disallow: /' and its public JSON endpoints return 403 "
    "to scripts since access was withdrawn in 2023. Official access requires "
    "an OAuth user login, which SMDPIS never performs or stores. Use the "
    "Mastodon or Bluesky connectors instead."
)
_LINKEDIN_REASON = (
    "LinkedIn prohibits automated access without express written permission "
    "(stated at the top of its robots.txt and in its User Agreement), and "
    "member content requires a logged-in session. SMDPIS will not attempt to "
    "bypass this — export your own LinkedIn data archive instead."
)
_META_REASON = (
    "Automated data collection on this platform is prohibited without express "
    "written permission (stated at the top of its robots.txt), and content "
    "requires a logged-in browser session. SMDPIS will not attempt to bypass "
    "this — use the platform's official export tool for your own data, or the "
    "Mastodon/Bluesky connectors for public posts."
)

BLOCKED_DOMAINS: dict[str, str] = {
    "x.com": _X_REASON,
    "twitter.com": _X_REASON,
    "reddit.com": _REDDIT_REASON,
    "linkedin.com": _LINKEDIN_REASON,
    "facebook.com": _META_REASON,
    "instagram.com": _META_REASON,
    "threads.net": _META_REASON,
    "threads.com": _META_REASON,
}


def blocked_reason(host: str) -> str | None:
    """Return the platform's stated reason if `host` is blanket-blocked."""
    for domain, reason in BLOCKED_DOMAINS.items():
        if host == domain or host.endswith("." + domain):
            return f"{host}: {reason}"
    return None

# Module-level politeness + robots caches (single-process dev server).
_last_hit: dict[str, float] = {}
_robots_cache: dict[str, tuple[float, urllib.robotparser.RobotFileParser]] = {}


@dataclass
class FetchedResource:
    """A single successfully retrieved document."""

    requested_url: str
    url: str
    filename: str
    content_type: str
    status_code: int
    size_bytes: int
    elapsed_ms: int
    fetched_at: str
    redirects: list[str] = field(default_factory=list)
    robots_allowed: bool = True
    content: bytes = b""

    def provenance(self) -> dict:
        """Machine-readable custody metadata recorded alongside the dataset."""
        return {
            "method": "fetch",
            "requested_url": self.requested_url,
            "final_url": self.url,
            "http_status": self.status_code,
            "content_type": self.content_type,
            "size_bytes": self.size_bytes,
            "redirects": self.redirects,
            "robots_allowed": self.robots_allowed,
            "fetched_at": self.fetched_at,
            "elapsed_ms": self.elapsed_ms,
            "user_agent": settings.user_agent,
        }


# ---------------------------------------------------------------------------
# URL policy
# ---------------------------------------------------------------------------

def validate_url(url: str) -> str:
    """Enforce the outbound URL policy. Returns the normalized URL."""
    if not url or not str(url).strip():
        raise ValidationFailed("A URL is required.")
    raw = str(url).strip()
    try:
        parts = urlparse(raw)
    except ValueError as exc:  # pragma: no cover - urlparse is permissive
        raise ValidationFailed(f"Malformed URL: {exc}") from exc

    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise ValidationFailed("Only http:// and https:// URLs may be collected.")
    if not parts.hostname:
        raise ValidationFailed("URL has no hostname.")
    if parts.username or parts.password:
        raise ValidationFailed("URLs embedding credentials are not permitted.")

    host = parts.hostname.lower().rstrip(".")
    # Before DNS: a known-blocked platform fails instantly, offline.
    blocked = blocked_reason(host)
    if blocked:
        raise FetchFailed(blocked, status_code=403)

    allowlist = settings.fetch_host_allowlist
    if allowlist and not any(host == a or host.endswith("." + a) for a in allowlist):
        raise ValidationFailed(
            f"Host '{host}' is not in the configured allow-list "
            "(SMDPIS_FETCH_HOST_ALLOWLIST)."
        )

    port = parts.port or (443 if parts.scheme.lower() == "https" else 80)
    _assert_public(host, port)
    return raw


def _assert_public(host: str, port: int) -> None:
    """Resolve `host` and reject it unless every answer is a public address."""
    if settings.fetch_allow_private:
        return
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ValidationFailed(f"Could not resolve host '{host}'.") from exc

    answers = {info[4][0] for info in infos}
    if not answers:
        raise ValidationFailed(f"Host '{host}' did not resolve to any address.")

    for answer in answers:
        ip = ipaddress.ip_address(answer.split("%")[0])
        if ip.version == 6 and ip.ipv4_mapped is not None:  # ::ffff:10.0.0.1
            ip = ip.ipv4_mapped
        if not ip.is_global:
            raise ValidationFailed(
                f"Host '{host}' resolves to a non-public address ({ip}). "
                "Internal, loopback and link-local targets are blocked."
            )


def assert_allowed(url: str) -> None:
    """Public entry point used by the crawler for candidate links."""
    validate_url(url)


# ---------------------------------------------------------------------------
# robots.txt
# ---------------------------------------------------------------------------

def robots_allowed(url: str) -> bool:
    if not settings.fetch_robots_obey:
        return True
    try:
        parts = urlparse(validate_url(url))
    except ValidationFailed:
        return False
    origin = f"{parts.scheme}://{parts.netloc}"
    if parts.path in ("", "/robots.txt"):
        # Fetching robots.txt itself never requires consulting robots.txt.
        return True

    now = time.time()
    cached = _robots_cache.get(origin)
    if cached and now - cached[0] < _ROBOTS_TTL_SECONDS:
        return cached[1].can_fetch(settings.user_agent, url)

    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(f"{origin}/robots.txt")
    try:
        with _client() as client:
            response = client.get(f"{origin}/robots.txt")
        if response.status_code == 200:
            parser.parse(response.text.splitlines())
        else:
            # Missing or erroring robots.txt → no restrictions published.
            parser.parse([])
    except (httpx.HTTPError, ValidationFailed, ValueError):
        parser.parse([])

    _robots_cache[origin] = (now, parser)
    return parser.can_fetch(settings.user_agent, url)


def clear_caches() -> None:
    """Test hook: reset politeness and robots caches."""
    _last_hit.clear()
    _robots_cache.clear()


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------

def _client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    return httpx.Client(
        timeout=settings.fetch_timeout,
        follow_redirects=False,
        headers={"User-Agent": settings.user_agent, "Accept": "*/*"},
        transport=transport,
    )


def _throttle(url: str) -> None:
    interval = settings.fetch_min_interval
    if interval <= 0:
        return
    host = urlparse(url).netloc.lower()
    now = time.monotonic()
    previous = _last_hit.get(host)
    if previous is not None and now - previous < interval:
        time.sleep(interval - (now - previous))
    _last_hit[host] = time.monotonic()


def _request(
    client: httpx.Client,
    url: str,
    *,
    max_bytes: int,
    max_redirects: int,
) -> tuple[int, dict, bytes, list[str]]:
    """GET `url`, following redirects manually and re-validating each hop."""
    current = validate_url(url)
    hops: list[str] = []
    for _ in range(max_redirects + 1):
        _throttle(current)
        with client.stream("GET", current) as response:
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location")
                if not location:
                    raise FetchFailed(
                        f"Redirect from {current} carried no Location header."
                    )
                nxt = urljoin(current, location)
                # Guard runs here: a redirect cannot reach a private address.
                nxt = validate_url(nxt)
                hops.append(nxt)
                current = nxt
                continue

            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > max_bytes:
                    raise ValidationFailed(
                        f"Response exceeds the {settings.fetch_max_mb} MB fetch limit."
                    )
            return response.status_code, dict(response.headers), bytes(body), hops

    raise FetchFailed(f"Too many redirects (limit {max_redirects}).", status_code=422)


# ---------------------------------------------------------------------------
# Filename / format resolution
# ---------------------------------------------------------------------------

_CONTENT_TYPE_EXT = {
    "text/csv": "csv",
    "application/csv": "csv",
    "application/json": "json",
    "application/x-ndjson": "jsonl",
    "application/jsonl": "jsonl",
    "application/x-jsonlines": "jsonl",
    "application/parquet": "parquet",
    "application/vnd.apache.parquet": "parquet",
}


def _extension_from_disposition(header: str) -> str | None:
    if not header:
        return None
    for part in header.split(";"):
        part = part.strip()
        if part.lower().startswith("filename="):
            value = part.split("=", 1)[1].strip().strip('"')
            suffix = Path(unquote(value)).suffix.lower().lstrip(".")
            return suffix or None
    return None


def _resolve_filename(url: str, headers: dict) -> str:
    """Work out a stored filename whose extension the ingest pipeline accepts."""
    content_type = (headers.get("content-type") or "").split(";")[0].strip().lower()

    candidates = [
        _extension_from_disposition(headers.get("content-disposition", "")),
        Path(unquote(urlparse(url).path)).suffix.lower().lstrip(".") or None,
        _CONTENT_TYPE_EXT.get(content_type),
    ]
    for ext in candidates:
        if ext and ext in settings.allowed_extensions:
            stem = safe_stem_from_url(url)
            return f"{stem}.{ext}"

    hint = content_type or "unknown content type"
    raise ValidationFailed(
        "The fetched resource is not a supported dataset format "
        f"({hint}). Allowed: {', '.join(sorted(settings.allowed_extensions))}."
    )


def safe_stem_from_url(url: str) -> str:
    import re

    name = Path(unquote(urlparse(url).path)).stem or "fetched"
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)[:80]
    return name or "fetched"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_url(
    url: str,
    *,
    transport: httpx.BaseTransport | None = None,
    respect_robots: bool = True,
    max_bytes: int | None = None,
) -> FetchedResource:
    """Download a public dataset file and return it with provenance metadata."""
    if not settings.fetch_enabled:
        raise FetchFailed(
            "Outbound collection is disabled (SMDPIS_FETCH_ENABLED=false).",
            status_code=403,
        )

    target = validate_url(url)
    allowed = robots_allowed(target) if respect_robots else True
    if not allowed:
        raise FetchFailed(
            f"robots.txt on {urlparse(target).netloc} disallows fetching this URL.",
            status_code=403,
        )

    limit = max_bytes or settings.fetch_max_mb * 1024 * 1024
    started = time.perf_counter()
    try:
        with _client(transport) as client:
            status, headers, body, hops = _request(
                client,
                target,
                max_bytes=limit,
                max_redirects=settings.fetch_max_redirects,
            )
    except ValidationFailed:
        raise
    except FetchFailed:
        raise
    except httpx.TimeoutException as exc:
        raise FetchFailed(f"Request to {url} timed out after {settings.fetch_timeout}s.") from exc
    except httpx.HTTPError as exc:
        raise FetchFailed(f"Request to {url} failed: {exc}") from exc

    if status >= 400:
        raise FetchFailed(f"{url} responded HTTP {status}.", status_code=422)
    if not body:
        raise FetchFailed(f"{url} returned an empty response.")

    final_url = hops[-1] if hops else target
    filename = _resolve_filename(final_url, headers)

    return FetchedResource(
        requested_url=url,
        url=final_url,
        filename=filename,
        content_type=(headers.get("content-type") or "").split(";")[0].strip().lower(),
        status_code=status,
        size_bytes=len(body),
        elapsed_ms=int((time.perf_counter() - started) * 1000),
        fetched_at=datetime.now(timezone.utc).isoformat(),
        redirects=hops,
        robots_allowed=allowed,
        content=body,
    )


def records_to_csv(records: list[dict], filename: str) -> bytes:
    """Serialize collected records to CSV bytes for the ingest pipeline."""
    import io

    import pandas as pd

    if not records:
        raise ValidationFailed("Collection returned no records.")
    df = pd.DataFrame(records)
    df = df.dropna(how="all")
    if df.empty:
        raise ValidationFailed("Collection returned no usable records.")
    buffer = io.StringIO()
    df.to_csv(buffer, index=False)
    return buffer.getvalue().encode("utf-8")


def fetch_document(
    url: str,
    *,
    transport: httpx.BaseTransport | None = None,
    respect_robots: bool = True,
    max_bytes: int | None = None,
) -> tuple[int, dict, bytes, str, list[str]]:
    """SSRF-guarded raw GET returning ``(status, headers, body, final_url, hops)``.

    Used by the crawler, which reads HTML rather than a dataset file and so must
    skip filename/format resolution.
    """
    if not settings.fetch_enabled:
        raise FetchFailed(
            "Outbound collection is disabled (SMDPIS_FETCH_ENABLED=false).",
            status_code=403,
        )
    target = validate_url(url)
    if respect_robots and not robots_allowed(target):
        raise FetchFailed(
            f"robots.txt on {urlparse(target).netloc} disallows fetching this URL.",
            status_code=403,
        )

    limit = max_bytes or settings.fetch_max_mb * 1024 * 1024
    try:
        with _client(transport) as client:
            status, headers, body, hops = _request(
                client, target, max_bytes=limit, max_redirects=settings.fetch_max_redirects
            )
    except ValidationFailed:
        raise
    except FetchFailed:
        raise
    except httpx.TimeoutException as exc:
        raise FetchFailed(f"Request to {url} timed out after {settings.fetch_timeout}s.") from exc
    except httpx.HTTPError as exc:
        raise FetchFailed(f"Request to {url} failed: {exc}") from exc

    final_url = hops[-1] if hops else target
    return status, headers, body, final_url, hops


def get_json(
    url: str,
    *,
    transport: httpx.BaseTransport | None = None,
    params: dict | None = None,
    respect_robots: bool = True,
) -> object:
    """SSRF-guarded JSON GET used by the official-platform source connectors."""
    if not settings.fetch_enabled:
        raise FetchFailed(
            "Outbound collection is disabled (SMDPIS_FETCH_ENABLED=false).",
            status_code=403,
        )
    target = validate_url(url)
    if respect_robots and not robots_allowed(target):
        raise FetchFailed(
            f"robots.txt on {urlparse(target).netloc} disallows fetching this URL.",
            status_code=403,
        )

    try:
        _throttle(target)
        with _client(transport) as client:
            response = client.get(target, params=params)
    except ValidationFailed:
        raise
    except httpx.TimeoutException as exc:
        raise FetchFailed(f"Request to {url} timed out after {settings.fetch_timeout}s.") from exc
    except httpx.HTTPError as exc:
        raise FetchFailed(f"Request to {url} failed: {exc}") from exc

    if response.status_code >= 400:
        raise FetchFailed(
            f"{url} responded HTTP {response.status_code}. The source may require "
            "authentication, may be rate-limiting this client, or a CDN/WAF may be "
            "blocking this network — the endpoint is reachable but refusing this "
            "request.",
            status_code=422,
        )
    try:
        return response.json()
    except ValueError as exc:
        raise FetchFailed(
            f"{url} returned HTTP {response.status_code} but not JSON "
            f"({response.headers.get('content-type', 'no content-type')}) — the source "
            "likely blocked this client."
        ) from exc
