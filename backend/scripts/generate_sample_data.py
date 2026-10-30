#!/usr/bin/env python3
"""Generate realistic synthetic social-media data for SMDPIS.

Creates ~10,000 post-level records across 1,000 synthetic accounts with:
  - multiple platforms, timestamps, text, engagement metrics
  - account-level features (followers, following, account age, frequency)
  - labels for supervised experiments (sentiment, misinformation, automation)

ALL data is synthetic. No real people, organizations, or private information
are represented. Domains use the reserved `.example` TLD.

Usage:
    python scripts/generate_sample_data.py --output ../data/sample \
        --posts 10000 --accounts 1000
"""
from __future__ import annotations

import argparse
import csv
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

RNG = random.Random(42)

PLATFORMS = ["x", "reddit", "mastodon", "threads", "youtube"]
PLATFORM_WEIGHTS = [0.34, 0.24, 0.14, 0.16, 0.12]

TOPICS = [
    "renewable energy", "remote work", "space exploration", "public transit",
    "mental health", "indie games", "ocean cleanup", "home gardening",
    "electric vehicles", "online learning", "urban cycling", "coffee culture",
    "museum exhibits", "wildlife conservation", "startup culture",
    "open-source software", "local food markets", "amateur astronomy",
]

LANGUAGES = ["en"] * 82 + ["es"] * 7 + ["fr"] * 6 + ["hi"] * 5

SYNTHETIC_DOMAINS = [
    "beacon-wire.example", "signal-daily.example", "veritas-post.example",
    "meridian-news.example", "coral-press.example", "northlight.example",
    "openledger-digest.example", "pulse-report.example",
    "social.example", "mediahub.example", "blogframe.example",
]

FAKE_DOMAINS = [
    "truth-now-today.example", "shocking-daily.example",
    "click-alerts-24.example", "viral-facts-global.example",
]

OUTLETS = [
    "Beacon Wire", "Signal Daily", "Veritas Post", "Meridian News",
    "Coral Press", "Northlight", "Pulse Report", "Community Desk",
]

HASHTAGS = [
    "tech", "health", "markets", "climate", "design", "science", "sports",
    "films", "travel", "food", "weekend", "threads", "daily", "focus",
]

POSITIVE_TEMPLATES = [
    "Loving the {topic} updates this week — {emoji} great progress everyone.",
    "{topic} is genuinely improving and it shows. {mention} check this out!",
    "Huge shout-out to the team working on {topic}. {emoji} {hashtag}",
    "Finally tried {topic} myself and wow, exceeded expectations {emoji}",
    "The {topic} community keeps inspiring me {emoji} {hashtag}",
    "Amazing write-up on {topic}: {url} — worth the read {mention}",
    "Bright spot today: {topic} results just came in and they look excellent {emoji}",
]

NEUTRAL_TEMPLATES = [
    "New {topic} data dropped today. Summary thread below {hashtag}",
    "Anyone else following the {topic} discussion? {mention}",
    "Reading about {topic} — mixed details so far. {url}",
    "Quick note on {topic}: here is what changed this week {hashtag}",
    "{topic} roundup for Monday {emoji} {url}",
    "Question for the {topic} folks: what tool are you using? {mention}",
    "Scheduled {topic} update going live at noon {hashtag}",
    "Comparing two {topic} approaches — notes here {url}",
]

NEGATIVE_TEMPLATES = [
    "Frustrated with how {topic} is being handled lately {emoji} {hashtag}",
    "The {topic} situation keeps getting worse and nobody is addressing it.",
    "Disappointed by the {topic} announcement today. {mention} thoughts?",
    "Not going to lie, {topic} has been a mess this week {emoji}",
    "Another setback for {topic} — details here {url} {hashtag}",
    "Struggled with {topic} all morning. Anyone else? {mention}",
]

MISINFO_TEMPLATES = [
    "SHOCKING: insiders say {topic} will be BANNED by Friday — share before deleted! {hashtag}",
    "Doctors HATE this {topic} trick that big companies don't want you to know {emoji} {url}",
    "Hidden truth about {topic} revealed by anonymous leaked memo {hashtag}",
    "You won't BELIEVE what {topic} experts just admitted on camera {emoji} {mention}",
    "URGENT: viral post claims {topic} causes 500% spike — no source provided {hashtag}",
    "Miracle {topic} cure spreading fast, mainstream outlets refusing to cover it {url}",
]

MISINFO_HEADLINES = [
    "Anonymous sources claim dramatic {topic} reversal coming this week",
    "Viral {topic} claim lacks any verifiable evidence, experts say",
    "Leaked memo allegedly shows secret {topic} plan",
    "Shocking {topic} statistic circulates without a traceable source",
]

HEADLINE_TEMPLATES = [
    "{Topic} sector sees steady movement this quarter",
    "What the latest {topic} numbers actually mean",
    "{topic}: a beginner's guide to the new rules",
    "Local {topic} initiative expands to three more districts",
]

BOT_PROMO_TEMPLATES = [
    "🚀 Level up your {topic} game — daily signals, zero fluff. Join now: {url}",
    "Discover the ultimate {topic} toolkit {emoji} Try it free today {hashtag}",
    "Don't miss out! {topic} masterclass starts tonight {url} {hashtag}",
    "Your daily {topic} digest is live {emoji} Subscribe for more {hashtag}",
    "Boost your {topic} results by 300% with this one method {emoji} {url}",
    "Automated {topic} insights delivered every hour {emoji} Follow for updates {hashtag}",
]

POSITIVE_EMOJI = ["😀", "🎉", "🔥", "💯", "🙌", "✨", "😍", "👏"]
NEGATIVE_EMOJI = ["😞", "😤", "🙄", "😒", "😩", "🤦"]
NEUTRAL_EMOJI = ["🙂", "📌", "📊", "🗓", "📝"]

PREFIXES = [
    "nova", "pixel", "urban", "amber", "cobalt", "drift", "ember", "fjord",
    "granite", "harbor", "indigo", "juniper", "kestrel", "lumen", "meadow",
    "nimbus", "onyx", "prairie", "quartz", "rivet", "summit", "tundra",
    "umbra", "vector", "willow", "zephyr", "atlas", "basil", "cinder", "delta",
]

NON_ENGLISH = {
    "es": [
        "Gran avance en {topic} esta semana {emoji} {hashtag}",
        " Leyendo sobre {topic}, datos interesantes {url}",
        "Frustrado con el rumbo de {topic} últimamente {emoji}",
    ],
    "fr": [
        "Beaucoup de progrès sur {topic} cette semaine {emoji} {hashtag}",
        "Discussion intéressante à propos de {topic} {mention}",
        "Déçu par les annonces sur {topic} aujourd'hui {emoji}",
    ],
    "hi": [
        "{topic} पर अच्छी खबर आई है {emoji} {hashtag}",
        "क्या कोई {topic} के बारे में पढ़ रहा है? {mention}",
        "{topic} की स्थिति ठीक नहीं है {emoji}",
    ],
}


def make_accounts(n: int) -> list[dict]:
    accounts = []
    used_names: set[str] = set()
    n_bots = max(1, int(n * 0.07))
    bot_idx = set(RNG.sample(range(n), n_bots))

    for i in range(n):
        while True:
            name = f"{RNG.choice(PREFIXES)}{RNG.randint(100, 9999)}"
            if name not in used_names:
                used_names.add(name)
                break
        is_bot = i in bot_idx
        language = RNG.choice(LANGUAGES)

        if is_bot:
            followers = RNG.randint(15, 600)
            following = RNG.randint(800, 4500)
            account_age = RNG.randint(10, 500)
            # a subset of bots mimic humans to keep the task non-trivial
            subtle = RNG.random() < 0.2
            style = "subtle_bot" if subtle else "bot"
        else:
            followers = int(RNG.lognormvariate(5.2, 1.4)) + 10
            following = int(RNG.lognormvariate(5.6, 1.1)) + 20
            account_age = RNG.randint(30, 3600)
            # a subset of humans post very routinely (scheduled content)
            style = "regular_human" if RNG.random() < 0.1 else "human"

        accounts.append(
            {
                "user_id": f"U{i + 1:04d}",
                "username": name,
                "platform": RNG.choices(PLATFORMS, PLATFORM_WEIGHTS)[0],
                "is_automated": 1 if is_bot else 0,
                "language": language,
                "followers": min(followers, 250000),
                "following": min(following, 5000),
                "account_age": account_age,
                "style": style,
                "topic": RNG.choice(TOPICS),
                "seed_hashtag": RNG.choice(HASHTAGS),
                "seed_url_domain": RNG.choice(SYNTHETIC_DOMAINS),
            }
        )
    return accounts


def allocate_counts(accounts: list[dict], total: int) -> None:
    weights = []
    for a in accounts:
        if a["style"] == "bot":
            weights.append(RNG.uniform(45, 75))
        elif a["style"] == "subtle_bot":
            weights.append(RNG.uniform(15, 35))
        elif a["style"] == "regular_human":
            weights.append(RNG.uniform(12, 30))
        else:
            weights.append(RNG.uniform(2, 14))
    raw = [w / sum(weights) * total for w in weights]
    counts = [max(1, int(r)) for r in raw]
    diff = total - sum(counts)
    idx = 0
    while diff != 0:
        i = idx % len(counts)
        if diff > 0:
            counts[i] += 1
            diff -= 1
        elif counts[i] > 1:
            counts[i] -= 1
            diff += 1
        idx += 1
    for a, c in zip(accounts, counts):
        a["post_count"] = c


def make_timestamps(account: dict, window_start: datetime, window_days: int) -> list[datetime]:
    n = account["post_count"]
    span_seconds = window_days * 86400
    style = account["style"]

    if style in {"bot", "subtle_bot"} and style == "bot":
        # Perfectly regular cadence → very high activity regularity.
        interval = span_seconds / (n + 1)
        start = window_start + timedelta(seconds=RNG.uniform(0, interval))
        stamps = [start + timedelta(seconds=interval * k) for k in range(n)]
    else:
        hours = [2, 3, 7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 18, 19, 20, 21, 22, 23]
        weights = [1, 1, 2, 4, 6, 7, 7, 6, 6, 5, 5, 6, 7, 8, 8, 7, 5, 3]
        stamps = []
        if style == "regular_human":
            interval = span_seconds / (n + 1)
            jitter = interval * 0.06
            start = window_start + timedelta(seconds=RNG.uniform(0, interval))
            stamps = [
                start + timedelta(seconds=interval * k + RNG.uniform(-jitter, jitter))
                for k in range(n)
            ]
        else:
            for _ in range(n):
                day_offset = RNG.uniform(0, span_seconds)
                hour = RNG.choices(hours, weights)[0]
                stamp = window_start + timedelta(seconds=day_offset)
                stamp = stamp.replace(hour=hour, minute=RNG.randint(0, 59),
                                      second=RNG.randint(0, 59))
                stamps.append(stamp)
        stamps.sort()

    end = window_start + timedelta(seconds=span_seconds)
    stamps = [
        s if s <= end else end - timedelta(seconds=RNG.uniform(60, 3600))
        for s in stamps
    ]
    stamps.sort()
    account["post_count"] = len(stamps)
    return stamps


def render(template: str, account: dict, all_usernames: list[str]) -> str:
    topic = account["topic"]
    other = RNG.choice(all_usernames)
    emoji_pool = POSITIVE_EMOJI
    if "Frustrated" in template or "worse" in template or "Disappointed" in template \
            or "Struggled" in template or "mess" in template or "setback" in template:
        emoji_pool = NEGATIVE_EMOJI
    elif "{topic}" in template and "SHOCK" not in template.upper():
        emoji_pool = NEUTRAL_EMOJI + POSITIVE_EMOJI
    text = template.format(
        topic=topic,
        Topic=topic.capitalize(),
        emoji=RNG.choice(emoji_pool),
        mention=f"@{other}",
        hashtag=f"#{RNG.choice(HASHTAGS)}",
        url=f"https://{account['seed_url_domain']}/{topic.replace(' ', '-')}",
    )
    return text


def pick_template(account: dict, sentiment: str, misinfo: int) -> tuple[str, str]:
    """Return (template, kind)."""
    if misinfo == 1:
        return RNG.choice(MISINFO_TEMPLATES), "misinfo"
    if account["style"] in {"bot", "subtle_bot"}:
        return RNG.choice(BOT_PROMO_TEMPLATES), "bot_promo"
    if account["language"] != "en" and RNG.random() < 0.7:
        pool = NON_ENGLISH[account["language"]]
        return RNG.choice(pool), "i18n"
    if sentiment == "positive":
        return RNG.choice(POSITIVE_TEMPLATES), "normal"
    if sentiment == "negative":
        return RNG.choice(NEGATIVE_TEMPLATES), "normal"
    return RNG.choice(NEUTRAL_TEMPLATES), "normal"


def generate(posts: int, accounts_n: int, window_days: int = 90) -> list[dict]:
    accounts = make_accounts(accounts_n)
    allocate_counts(accounts, posts)
    usernames = [a["username"] for a in accounts]

    window_end = datetime.now(timezone.utc)
    window_start = window_end - timedelta(days=window_days)

    rows: list[dict] = []
    post_seq = 0

    for account in accounts:
        stamps = make_timestamps(account, window_start, window_days)
        n = len(stamps)

        # per-account engagement character
        if account["is_automated"]:
            base_likes = RNG.uniform(0.5, 6.0)
            viral_boost = 0.4
        else:
            base_likes = RNG.uniform(3.0, 40.0) * (1 + account["followers"] / 4000)
            viral_boost = RNG.uniform(0.5, 3.0)

        # account-level posting frequency
        span_days = max(
            (stamps[-1] - stamps[0]).total_seconds() / 86400 if n > 1 else 1.0, 1e-6
        )
        freq = n / max(span_days, 1.0)

        for k, stamp in enumerate(stamps):
            post_seq += 1

            # labels
            sentiment = RNG.choices(
                ["positive", "neutral", "negative"], weights=[45, 35, 20]
            )[0]
            misinfo = 1 if RNG.random() < 0.11 else 0

            template, kind = pick_template(account, sentiment, misinfo)

            # curated templates imply their own sentiment when misinfo/bot/i18n
            if kind == "misinfo":
                sentiment = RNG.choice(["negative", "positive", "neutral"])
            elif kind == "bot_promo":
                sentiment = "positive"
            elif kind == "i18n":
                if "Frustrado" in template or "Déçu" in template or "ठीक नहीं" in template:
                    sentiment = "negative"
                else:
                    sentiment = RNG.choice(["positive", "neutral"])

            text = render(template, account, usernames)

            # interactions
            reply_to = ""
            shared_from = ""
            if RNG.random() < 0.14:
                other = RNG.choice(usernames)
                reply_to = other
                text = f"@{other} " + text
            if RNG.random() < 0.10:
                other = RNG.choice(usernames)
                shared_from = other
                text = f"RT @{other}: " + text

            has_link = RNG.random() < (0.55 if account["is_automated"] else 0.28)
            domain = (
                RNG.choice(FAKE_DOMAINS) if misinfo == 1 and has_link
                else account["seed_url_domain"]
            )
            url = f"https://{domain}/p/{account['username']}/{post_seq}" if has_link else ""
            if has_link and f"https://{domain}" not in text:
                text = f"{text} {url}".strip()

            if kind == "misinfo" or RNG.random() < 0.4:
                if misinfo == 1:
                    headline = RNG.choice(MISINFO_HEADLINES).format(topic=account["topic"])
                else:
                    headline = RNG.choice(HEADLINE_TEMPLATES).format(
                        topic=account["topic"], Topic=account["topic"].capitalize()
                    )
            else:
                headline = ""

            likes = max(0, int(RNG.gauss(base_likes, base_likes * viral_boost + 1)))
            comments = max(0, int(likes * RNG.uniform(0.0, 0.25)))
            shares = max(0, int(likes * RNG.uniform(0.0, 0.18)))
            if account["is_automated"]:
                likes = int(likes * RNG.uniform(0.1, 0.6))

            rows.append(
                {
                    "post_id": f"P{post_seq:06d}",
                    "user_id": account["user_id"],
                    "username": account["username"],
                    "platform": account["platform"],
                    "text": text,
                    "headline": headline,
                    "url": url,
                    "domain": domain if url else "",
                    "source": RNG.choice(OUTLETS) if url else "",
                    "timestamp": stamp.strftime("%Y-%m-%d %H:%M:%S%z"),
                    "likes": likes,
                    "comments": comments,
                    "shares": shares,
                    "followers": account["followers"],
                    "following": account["following"],
                    "account_age": account["account_age"],
                    "post_count": n,
                    "posting_frequency": round(freq, 4),
                    "language": account["language"],
                    "label": sentiment,
                    "misinfo_label": misinfo,
                    "is_automated": account["is_automated"],
                    "reply_to_username": reply_to,
                    "shared_from_username": shared_from,
                }
            )

    rows.sort(key=lambda r: r["timestamp"])
    return rows


FIELDNAMES = [
    "post_id", "user_id", "username", "platform", "text", "headline", "url",
    "domain", "source", "timestamp", "likes", "comments", "shares",
    "followers", "following", "account_age", "post_count", "posting_frequency",
    "language", "label", "misinfo_label", "is_automated",
    "reply_to_username", "shared_from_username",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate SMDPIS synthetic sample data")
    parser.add_argument("--output", default="../data/sample", help="Output directory")
    parser.add_argument("--posts", type=int, default=10000)
    parser.add_argument("--accounts", type=int, default=1000)
    parser.add_argument("--window-days", type=int, default=90)
    args = parser.parse_args()

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "smdp_posts.csv"

    rows = generate(args.posts, args.accounts, args.window_days)
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    accounts = {r["username"] for r in rows}
    bots = {r["username"] for r in rows if r["is_automated"] == 1}
    print(f"Wrote {len(rows)} records -> {out_path}")
    print(f"Accounts: {len(accounts)} (automated: {len(bots)})")
    print(f"Platforms: {sorted({r['platform'] for r in rows})}")
    print(f"Sentiment labels: {sorted({r['label'] for r in rows})}")
    print(f"Misinfo positives: {sum(r['misinfo_label'] for r in rows)}")


if __name__ == "__main__":
    main()
