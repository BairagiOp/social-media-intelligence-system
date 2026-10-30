"""Dataset profiling: statistics shown on the Dataset Profile page."""
from __future__ import annotations

from collections import Counter

import numpy as np
import pandas as pd

from app.utils.column_detect import resolve

LANG_BY_CONTENT = [
    ("es", [" el ", " la ", " que ", " los ", " gracias ", " muy "]),
    ("fr", [" le ", " les ", " des ", " une ", " avec ", " merci "]),
    ("hi", ["ह", "है", "के", "में", "और"]),
]


def _language_guess(texts: list[str], declared: pd.Series | None) -> dict:
    if declared is not None and declared.notna().any():
        counts = Counter(str(v).lower() for v in declared.dropna().tolist())
        if counts:
            total = sum(counts.values())
            return {k: round(v / total, 4) for k, v in counts.most_common(12)}
    counts = Counter()
    for text in texts[:4000]:
        lowered = f" {str(text).lower()} "
        guessed = "en"
        for lang, signals in LANG_BY_CONTENT:
            if any(s in lowered for s in signals):
                guessed = lang
                break
        counts[guessed] += 1
    total = sum(counts.values()) or 1
    return {k: round(v / total, 4) for k, v in counts.most_common(12)}


def _sentiment_distribution(texts: list[str]) -> dict:
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    except Exception:
        try:
            from nltk.sentiment import vader as _vader_mod  # noqa: F401
            from nltk.sentiment.vader import SentimentIntensityAnalyzer
        except Exception:
            return {}
    try:
        analyzer = SentimentIntensityAnalyzer()
    except Exception:
        return {}
    labels = Counter()
    compounds = []
    sample = texts[:5000]
    for text in sample:
        score = analyzer.polarity_scores(str(text))["compound"]
        compounds.append(score)
        labels["positive" if score >= 0.05 else "negative" if score <= -0.05 else "neutral"] += 1
    total = sum(labels.values()) or 1
    return {
        "labels": {k: round(v / total, 4) for k, v in labels.most_common()},
        "counts": dict(labels),
        "mean_compound": round(float(np.mean(compounds)), 4) if compounds else 0.0,
    }


def build_profile(df: pd.DataFrame, mapping: dict[str, str]) -> dict:
    """Compute the full dataset profile used by the UI."""
    total_records = int(len(df))
    missing = {c: int(df[c].isna().sum()) for c in df.columns}
    missing_pct = {
        c: (round(m / total_records, 4) if total_records else 0.0)
        for c, m in missing.items()
    }
    duplicates = int(df.duplicated().sum())

    text_col = resolve(mapping, "text")
    texts = df[text_col].dropna().astype(str).tolist() if text_col else []
    text_lengths = [len(t) for t in texts]

    ts_col = resolve(mapping, "timestamp")
    date_range = None
    if ts_col:
        try:
            ts = pd.to_datetime(df[ts_col], utc=True, errors="coerce").dropna()
            if len(ts):
                date_range = {
                    "min": ts.min().isoformat(),
                    "max": ts.max().isoformat(),
                }
        except Exception:
            date_range = None

    platform_col = resolve(mapping, "platform")
    platform_dist = {}
    if platform_col:
        platform_dist = {
            str(k): int(v)
            for k, v in df[platform_col].value_counts().head(15).items()
        }

    user_col = resolve(mapping, "username") or resolve(mapping, "user_id")
    unique_users = int(df[user_col].nunique()) if user_col else 0

    lang_col = resolve(mapping, "language")
    language_dist = _language_guess(
        texts, df[lang_col] if lang_col else None
    )

    # Class distributions for every candidate label column.
    class_distributions: dict[str, dict] = {}
    for canonical in ("label", "misinfo_label", "is_automated"):
        col = resolve(mapping, canonical)
        if col and col in df.columns:
            vc = df[col].value_counts(dropna=True).head(20)
            class_distributions[canonical] = {
                "column": col,
                "counts": {str(k): int(v) for k, v in vc.items()},
            }

    sentiment = _sentiment_distribution(texts) if texts else {}

    dtypes = {c: str(df[c].dtype) for c in df.columns}

    return {
        "records": total_records,
        "columns_count": int(df.shape[1]),
        "column_names": list(df.columns),
        "dtypes": dtypes,
        "missing_values": missing,
        "missing_pct": missing_pct,
        "duplicate_records": duplicates,
        "unique_users": unique_users,
        "platform_distribution": platform_dist,
        "date_range": date_range,
        "language_distribution": language_dist,
        "avg_text_length": round(float(np.mean(text_lengths)), 2) if text_lengths else 0.0,
        "median_text_length": float(np.median(text_lengths)) if text_lengths else 0.0,
        "sentiment_distribution": sentiment,
        "class_distributions": class_distributions,
        "column_map": mapping,
    }
