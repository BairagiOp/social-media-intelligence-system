"""VADER sentiment analysis.

Sentiment scores describe the tone of text. They are NOT evidence of intent
or wrongdoing — every API response carries an explicit disclaimer.
"""
from __future__ import annotations

from collections import defaultdict

import pandas as pd

from app.utils.column_detect import resolve
from app.utils.errors import ValidationFailed

DISCLAIMER = (
    "Sentiment reflects the tone of the text only. It is not evidence of "
    "intent, coordination, or wrongdoing."
)

_analyzer = None


def _get_analyzer():
    global _analyzer
    if _analyzer is not None:
        return _analyzer
    from app.utils.text_cleaning import ensure_nltk_data

    ensure_nltk_data()
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    except Exception:
        from nltk.sentiment.vader import SentimentIntensityAnalyzer
    _analyzer = SentimentIntensityAnalyzer()
    return _analyzer


def score_texts(texts: list[str]) -> list[dict]:
    analyzer = _get_analyzer()
    results = []
    for text in texts:
        scores = analyzer.polarity_scores(str(text))
        results.append(
            {
                "positive": scores["pos"],
                "negative": scores["neg"],
                "neutral": scores["neu"],
                "compound": scores["compound"],
            }
        )
    return results


def label_for_compound(compound: float) -> str:
    if compound >= 0.05:
        return "positive"
    if compound <= -0.05:
        return "negative"
    return "neutral"


def vader_labels(texts: list[str]) -> list[str]:
    return [label_for_compound(r["compound"]) for r in score_texts(texts)]


def analyze_dataset(df: pd.DataFrame, mapping: dict) -> dict:
    text_col = resolve(mapping, "text") or resolve(mapping, "text_clean")
    if not text_col or text_col not in df.columns:
        raise ValidationFailed(
            "No text column detected for sentiment analysis. Map a text column first."
        )

    texts = df[text_col].fillna("").astype(str)
    scores = score_texts(texts.tolist())
    compounds = [s["compound"] for s in scores]
    labels = [label_for_compound(c) for c in compounds]

    total = len(labels) or 1
    counts = {"positive": 0, "neutral": 0, "negative": 0}
    for lab in labels:
        counts[lab] = counts.get(lab, 0) + 1

    user_col = resolve(mapping, "username")
    platform_col = resolve(mapping, "platform")
    ts_col = resolve(mapping, "timestamp")

    ts = (
        pd.to_datetime(df[ts_col], utc=True, errors="coerce")
        if ts_col and ts_col in df.columns
        else pd.Series([pd.NaT] * len(df), index=df.index)
    )

    # Timeline
    timeline_map: dict[str, list] = defaultdict(list)
    for date, comp in zip(ts.dt.strftime("%Y-%m-%d"), compounds):
        if isinstance(date, str):
            timeline_map[date].append(comp)
    timeline = [
        {
            "date": d,
            "mean_compound": round(sum(v) / len(v), 4),
            "count": len(v),
        }
        for d, v in sorted(timeline_map.items())
    ]

    # By platform
    by_platform = {}
    if platform_col and platform_col in df.columns:
        work = pd.DataFrame(
            {platform_col: df[platform_col].fillna("unknown"), "compound": compounds}
        )
        grouped = work.groupby(platform_col)["compound"].agg(["mean", "count"])
        by_platform = {
            str(idx): {"mean_compound": round(float(row["mean"]), 4), "count": int(row["count"])}
            for idx, row in grouped.iterrows()
        }

    # By user (top 20 by volume)
    by_user = {}
    if user_col and user_col in df.columns:
        work = pd.DataFrame(
            {user_col: df[user_col].fillna("unknown"), "compound": compounds}
        )
        counts_by_user = work[user_col].value_counts().head(20)
        grouped = work.groupby(user_col)["compound"].mean()
        by_user = {
            str(idx): {
                "mean_compound": round(float(grouped[idx]), 4),
                "count": int(counts_by_user.get(idx, 0)),
            }
            for idx in counts_by_user.index
        }

    # Extreme posts
    order = sorted(range(len(compounds)), key=lambda i: compounds[i])
    negative_idx = order[:10]
    positive_idx = list(reversed(order[-10:]))

    def _post(i: int) -> dict:
        item = {
            "text": str(texts.iloc[i])[:500],
            "compound": round(compounds[i], 4),
            "label": labels[i],
        }
        if user_col:
            item["username"] = str(df[user_col].iloc[i])
        if platform_col:
            item["platform"] = str(df[platform_col].iloc[i])
        if ts_col:
            item["timestamp"] = (
                ts.iloc[i].isoformat() if pd.notna(ts.iloc[i]) else None
            )
        return item

    return {
        "disclaimer": DISCLAIMER,
        "total": int(len(labels)),
        "overall": {
            "counts": counts,
            "ratios": {k: round(v / total, 4) for k, v in counts.items()},
            "mean_compound": round(sum(compounds) / total, 4) if compounds else 0.0,
        },
        "timeline": timeline,
        "by_platform": by_platform,
        "by_user": by_user,
        "most_positive": [_post(i) for i in positive_idx],
        "most_negative": [_post(i) for i in negative_idx],
    }
