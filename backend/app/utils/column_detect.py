"""Automatic detection of canonical social-media columns."""
from __future__ import annotations

import re

CANONICAL_COLUMNS: dict[str, list[str]] = {
    "user_id": ["user_id", "userid", "uid", "account_id", "author_id", "user"],
    "username": [
        "username", "user_name", "screen_name", "handle", "author",
        "account", "profile", "creator",
    ],
    "platform": ["platform", "source_platform", "network", "app", "site", "channel"],
    "text": [
        "text", "tweet", "post", "content", "body", "comment", "message",
        "full_text", "post_text", "caption",
    ],
    "headline": ["headline", "title", "subject"],
    "timestamp": [
        "timestamp", "created_at", "date", "datetime", "time", "posted_at",
        "publish_date", "published_at", "ts",
    ],
    "followers": ["followers", "follower_count", "friends_count_followers", "fans"],
    "following": ["following", "followees", "following_count"],
    "likes": ["likes", "favorite_count", "favourites", "like_count", "upvotes"],
    "comments": ["comments", "reply_count", "replies", "comment_count"],
    "shares": ["shares", "retweets", "retweet_count", "reposts", "share_count"],
    "account_age": ["account_age", "account_age_days", "age_days", "account_created"],
    "post_count": ["post_count", "posts_count", "statuses_count", "num_posts"],
    "posting_frequency": ["posting_frequency", "posts_per_day", "frequency"],
    "label": ["label", "sentiment", "sentiment_label", "class", "target", "y"],
    "misinfo_label": [
        "misinfo_label", "misinformation", "is_fake", "fake", "fake_label",
        "reliability_label", "rating",
    ],
    "is_automated": [
        "is_automated", "is_bot", "bot_label", "bot", "account_type",
        "automated", "is_automated_account",
    ],
    "url": ["url", "link", "post_url", "permalink"],
    "domain": ["domain", "website", "host", "site_domain"],
    "source": ["source", "outlet", "publisher", "origin"],
    "language": ["language", "lang", "locale"],
    "reply_to_username": ["reply_to_username", "in_reply_to_screen_name", "reply_to"],
    "shared_from_username": ["shared_from_username", "retweeted_from", "shared_from"],
}

_NORMALIZE_RE = re.compile(r"[^a-z0-9]")


def _normalize(name: str) -> str:
    return _NORMALIZE_RE.sub("", str(name).strip().lower())


def detect_columns(columns: list[str]) -> dict[str, str]:
    """Return {canonical: actual_column} for every confidently detected column."""
    normalized = {_normalize(c): c for c in columns}
    mapping: dict[str, str] = {}
    used: set[str] = set()
    for canonical, candidates in CANONICAL_COLUMNS.items():
        for candidate in candidates:
            key = _normalize(candidate)
            if key in normalized and normalized[key] not in used:
                mapping[canonical] = normalized[key]
                used.add(normalized[key])
                break
    return mapping


def apply_mapping(columns: list[str], mapping: dict[str, str]) -> dict[str, str]:
    """Merge a user-provided mapping, validating against actual columns."""
    valid = {c for c in columns}
    merged = detect_columns(columns)
    for canonical, actual in (mapping or {}).items():
        if actual in (None, "", "auto"):
            merged.pop(canonical, None)
        elif actual in valid:
            merged[canonical] = actual
    return merged


def resolve(mapping: dict[str, str], canonical: str) -> str | None:
    return mapping.get(canonical)
