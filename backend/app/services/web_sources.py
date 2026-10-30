"""Official public API connectors (Phase 2 of web collection).

These talk to *documented, unauthenticated public read endpoints* of platforms
that publish them — not to rendered HTML behind a login:

* Mastodon   ``/api/v1/tags/<tag>/statuses`` (any instance, no auth)
* Bluesky    ``app.bsky.feed.searchPosts``

Reddit's public JSON endpoints were withdrawn in 2023 (403 to scripts, and
``robots.txt`` now publishes ``Disallow: /`` for all agents), so no Reddit
connector is offered: official access requires an OAuth user login, which
SMDPIS deliberately never performs or stores.

Every request still passes the SSRF guard in :mod:`app.services.fetch_service`
and honours ``robots.txt``. Credentials are never required and never stored.
Records are normalized to SMDPIS canonical columns so the standard ingest,
profiling and ML pipeline applies unchanged.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import quote

import httpx

from app.config import settings
from app.services.fetch_service import get_json
from app.utils.errors import ValidationFailed

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

CollectFn = Callable[[dict, httpx.BaseTransport | None], list[dict]]


def strip_html(value: str | None) -> str:
    """Reduce markup to plain text (Mastodon posts are HTML bodies)."""
    if not value:
        return ""
    text = _TAG_RE.sub(" ", str(value))
    text = html.unescape(text)
    return _WS_RE.sub(" ", text).strip()


def _limit(params: dict) -> int:
    try:
        value = int(params.get("limit") or 100)
    except (TypeError, ValueError):
        value = 100
    return max(1, min(value, settings.collect_max_items))


def _require(params: dict, name: str, label: str) -> str:
    value = str(params.get(name) or "").strip()
    if not value:
        raise ValidationFailed(f"'{label}' is required for this source.")
    return value


# ---------------------------------------------------------------------------
# Mastodon
# ---------------------------------------------------------------------------

def collect_mastodon(params: dict, transport: httpx.BaseTransport | None = None) -> list[dict]:
    instance = _require(params, "target", "Instance").strip().rstrip("/")
    instance = instance.removeprefix("https://").removeprefix("http://")
    tag = _require(params, "query", "Hashtag").lstrip("#")
    limit = _limit(params)

    host = instance.split("/")[0]
    if "/" in instance.replace(host, "", 1):
        raise ValidationFailed("Instance must be a bare hostname, e.g. 'mastodon.social'.")

    url = f"https://{host}/api/v1/tags/{quote(tag, safe='')}/statuses"
    payload = get_json(
        url, transport=transport, params={"limit": str(limit)}
    )

    records: list[dict] = []
    for status in payload or []:
        account = (status or {}).get("account") or {}
        records.append(
            {
                "user_id": account.get("id"),
                "username": account.get("username") or account.get("acct"),
                "platform": "mastodon",
                "text": strip_html(status.get("content")),
                "headline": None,
                "timestamp": status.get("created_at"),
                "likes": status.get("favourites_count"),
                "comments": status.get("replies_count"),
                "shares": status.get("reblogs_count"),
                "url": status.get("url") or status.get("uri"),
                "domain": host,
                "source": f"#{tag}@{host}",
                "language": status.get("language"),
                "post_count": account.get("statuses_count"),
                "followers": account.get("followers_count"),
                "following": account.get("following_count"),
                "collected_via": "mastodon_public_api",
            }
        )
    return records


# ---------------------------------------------------------------------------
# Bluesky
# ---------------------------------------------------------------------------

def _bsky_url(uri: str | None, handle: str | None) -> str | None:
    if not uri or not uri.startswith("at://"):
        return uri
    parts = uri.split("/")
    if len(parts) < 5:
        return uri
    rkey = parts[-1]
    return f"https://bsky.app/profile/{handle or parts[2]}/post/{rkey}"


def collect_bluesky(params: dict, transport: httpx.BaseTransport | None = None) -> list[dict]:
    query = _require(params, "query", "Search query")
    limit = _limit(params)

    payload = get_json(
        "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts",
        transport=transport,
        params={"q": query, "limit": str(limit), "sort": "top"},
    )

    records: list[dict] = []
    for item in (payload or {}).get("posts") or []:
        author = (item or {}).get("author") or {}
        record = item.get("record") or {}
        handle = author.get("handle")
        records.append(
            {
                "user_id": author.get("did"),
                "username": handle or author.get("displayName"),
                "platform": "bluesky",
                "text": (record.get("text") or "").strip(),
                "headline": None,
                "timestamp": item.get("indexedAt") or record.get("createdAt"),
                "likes": item.get("likeCount"),
                "comments": item.get("replyCount"),
                "shares": item.get("repostCount"),
                "url": _bsky_url(item.get("uri"), handle),
                "domain": "bsky.app",
                "source": "bluesky_search",
                "language": record.get("langs", [None])[0] if record.get("langs") else None,
                "followers": author.get("followersCount"),
                "post_count": author.get("postsCount"),
                "collected_via": "bluesky_public_api",
            }
        )
    return records


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SourceSpec:
    id: str
    label: str
    description: str
    endpoint: str
    auth_required: bool
    license_note: str
    params: list[dict] = field(default_factory=list)
    collect: CollectFn = None  # type: ignore[assignment]


SOURCES: dict[str, SourceSpec] = {
    "mastodon": SourceSpec(
        id="mastodon",
        label="Mastodon (public tag API)",
        description="Public statuses carrying a hashtag, from any Mastodon instance.",
        endpoint="<instance>/api/v1/tags/<tag>/statuses",
        auth_required=False,
        license_note="Public statuses; instance operators set their own terms.",
        params=[
            {"name": "target", "label": "Instance", "placeholder": "mastodon.social",
             "required": True},
            {"name": "query", "label": "Hashtag", "placeholder": "opensource", "required": True},
            {"name": "limit", "label": "Max posts", "type": "number", "default": 100},
        ],
        collect=collect_mastodon,
    ),
    "bluesky": SourceSpec(
        id="bluesky",
        label="Bluesky (public search API)",
        description="Public posts matching a query via the app.bsky.feed.searchPosts XRPC.",
        endpoint="public.api.bsky.app/xrpc/app.bsky.feed.searchPosts",
        auth_required=False,
        license_note="Public posts; subject to Bluesky's API terms.",
        params=[
            {"name": "query", "label": "Search query", "placeholder": "machine learning",
             "required": True},
            {"name": "limit", "label": "Max posts", "type": "number", "default": 100},
        ],
        collect=collect_bluesky,
    ),
}


def list_sources() -> list[dict]:
    """Catalog payload for the frontend source picker."""
    return [
        {
            "id": s.id,
            "label": s.label,
            "description": s.description,
            "endpoint": s.endpoint,
            "auth_required": s.auth_required,
            "license_note": s.license_note,
            "params": s.params,
        }
        for s in SOURCES.values()
    ]


def collect(source_id: str, params: dict, transport: httpx.BaseTransport | None = None) -> list[dict]:
    spec = SOURCES.get(source_id)
    if not spec:
        raise ValidationFailed(
            f"Unknown source '{source_id}'. Available: {', '.join(sorted(SOURCES))}."
        )
    return spec.collect(params or {}, transport)
