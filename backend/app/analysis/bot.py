"""Transparent, feature-based automated-account likelihood analysis.

All outputs are model-derived estimates with explanations. The system never
claims an account "is a bot" — it reports an automated-account likelihood
score produced by a trained classifier.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from app.utils.column_detect import resolve
from app.utils.errors import ModelNotTrained, ValidationFailed

logger = logging.getLogger(__name__)

DISCLAIMER = (
    "Automated-account likelihood is a model estimate derived from public "
    "profile and posting-pattern features. It is not proof that an account "
    "is automated; human review is required."
)

FEATURE_COLUMNS = [
    "followers",
    "following",
    "follower_following_ratio",
    "post_count",
    "posting_frequency",
    "avg_interval_hours",
    "avg_text_length",
    "dup_content_ratio",
    "engagement_ratio",
    "activity_regularity",
    "account_age",
]

DEFAULT_LABEL_CANDIDATES = ["is_automated", "is_bot", "bot_label", "label"]


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def build_account_features(df: pd.DataFrame, mapping: dict) -> pd.DataFrame:
    """Aggregate post-level rows into account-level feature vectors."""
    user_col = resolve(mapping, "username") or resolve(mapping, "user_id")
    if not user_col or user_col not in df.columns:
        raise ValidationFailed(
            "Bot detection requires a username/user_id column. Map one first."
        )

    work = df.copy()
    ts_col = resolve(mapping, "timestamp")
    ts = (
        pd.to_datetime(work[ts_col], utc=True, errors="coerce")
        if ts_col and ts_col in work.columns
        else pd.Series([pd.NaT] * len(work), index=work.index)
    )
    work["_ts"] = ts

    text_col = resolve(mapping, "text") or resolve(mapping, "text_clean")
    work["_text"] = (
        work[text_col].fillna("").astype(str) if text_col in work.columns else ""
    )

    def _first(col: str) -> pd.Series | None:
        src = resolve(mapping, col)
        return _numeric(work[src]) if src in work.columns else None

    followers = _first("followers")
    following = _first("following")
    likes = _first("likes")
    comments = _first("comments")
    shares = _first("shares")
    account_age = _first("account_age")

    if likes is not None or comments is not None or shares is not None:
        engagement = (
            (likes if likes is not None else 0)
            + 2 * (comments if comments is not None else 0)
            + 3 * (shares if shares is not None else 0)
        )
    else:
        engagement = pd.Series(0.0, index=work.index)
    work["_engagement"] = engagement

    rows: list[dict] = []
    for user, grp in work.groupby(user_col, sort=False):
        n = len(grp)
        ts_vals = grp["_ts"].dropna().sort_values()

        if len(ts_vals) >= 2:
            diffs = ts_vals.diff().dt.total_seconds().dropna() / 3600.0
            avg_interval = float(diffs.mean()) if len(diffs) else 0.0
            span_days = max(
                (ts_vals.iloc[-1] - ts_vals.iloc[0]).total_seconds() / 86400.0, 1e-6
            )
            posting_frequency = n / max(span_days, 1.0)
            mean_diff = float(diffs.mean()) if len(diffs) else 0.0
            std_diff = float(diffs.std(ddof=0)) if len(diffs) else 0.0
            cv = std_diff / mean_diff if mean_diff > 1e-9 else 0.0
            activity_regularity = float(1.0 / (1.0 + cv))
        else:
            avg_interval = 0.0
            posting_frequency = float(n)
            activity_regularity = 0.5

        texts = grp["_text"]
        uniq = texts.nunique() if n else 1
        dup_ratio = float(1.0 - (uniq / n)) if n else 0.0
        avg_text_len = float(texts.str.len().mean()) if n else 0.0

        f = float(followers.loc[grp.index].median()) if followers is not None else np.nan
        fg = float(following.loc[grp.index].median()) if following is not None else np.nan
        age = float(account_age.loc[grp.index].median()) if account_age is not None else np.nan
        eng = float(grp["_engagement"].mean())

        rows.append(
            {
                "username": str(user),
                "followers": f if np.isfinite(f) else 0.0,
                "following": fg if np.isfinite(fg) else 0.0,
                "follower_following_ratio": (
                    float(f / fg) if fg and np.isfinite(fg) and fg != 0 else (float(f) if np.isfinite(f) else 0.0)
                ),
                "post_count": float(n),
                "posting_frequency": float(posting_frequency),
                "avg_interval_hours": float(avg_interval),
                "avg_text_length": avg_text_len,
                "dup_content_ratio": dup_ratio,
                "engagement_ratio": float(eng / f) if np.isfinite(f) and f > 0 else 0.0,
                "activity_regularity": activity_regularity,
                "account_age": age if np.isfinite(age) else 0.0,
            }
        )

    features = pd.DataFrame(rows)

    # Attach ground-truth label when the dataset provides one.
    label_src = None
    for candidate in DEFAULT_LABEL_CANDIDATES:
        col = resolve(mapping, candidate)
        if col and col in work.columns:
            label_src = col
            break
    if label_src:
        labels = (
            work[label_src]
            .map({True: 1, False: 0, "True": 1, "False": 0, "true": 1, "false": 0})
        )
        labels = pd.to_numeric(labels, errors="coerce")
        label_by_user = labels.groupby(work[user_col]).median()
        features["label"] = features["username"].map(label_by_user).round().astype(int)

    features = features.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return features


def predict_accounts(features: pd.DataFrame, artifact: dict) -> dict:
    """Score accounts with the active model and explain each score."""
    model = artifact["model"]
    used_features: list[str] = artifact.get("features") or [
        c for c in FEATURE_COLUMNS if c in features.columns
    ]
    X = features[used_features].replace([np.inf, -np.inf], np.nan).fillna(0.0)

    proba_all = model.predict_proba(X)
    classes = list(getattr(model, "classes_", [0, 1]))
    bot_idx = classes.index(1) if 1 in classes else len(classes) - 1
    proba = proba_all[:, bot_idx]

    stats = artifact.get("feature_stats") or {}
    means = np.array(stats.get("mean") or X.mean().tolist())
    stds = np.array(stats.get("std") or (X.std().replace(0, 1)).tolist())
    stds = np.where(np.asarray(stds, dtype=float) == 0, 1.0, stds)

    weights = artifact.get("contribution_weights")
    if weights is None:
        est = artifact.get("model_type", "")
        clf = model
        if hasattr(clf, "coef_"):
            weights = np.asarray(clf.coef_).reshape(-1)[: len(used_features)]
        elif hasattr(clf, "feature_importances_"):
            weights = np.asarray(clf.feature_importances_).reshape(-1)[: len(used_features)]
        else:
            weights = np.ones(len(used_features))
    weights = np.asarray(weights, dtype=float)

    accounts = []
    for position, (i, row) in enumerate(X.iterrows()):
        values = row.to_numpy(dtype=float)
        z = (values - means) / stds
        contributions = weights * z
        order = np.argsort(np.abs(contributions))[::-1][:6]
        explanation = [
            {
                "feature": used_features[j],
                "value": round(float(values[j]), 4),
                "contribution": round(float(contributions[j]), 4),
            }
            for j in order
        ]
        score = float(proba[position])
        accounts.append(
            {
                "username": str(features.loc[i, "username"]),
                "score": round(score, 4),
                "likelihood_band": _band(score),
                "classification": "LIKELY_AUTOMATED" if score >= 0.5 else "LIKELY_HUMAN",
                "features": {k: round(float(v), 4) for k, v in zip(used_features, values)},
                "feature_contributions": explanation,
            }
        )

    accounts.sort(key=lambda a: a["score"], reverse=True)
    buckets = [0] * 10
    for a in accounts:
        buckets[min(9, int(a["score"] * 10))] += 1

    return {
        "disclaimer": DISCLAIMER,
        "model": {
            "name": artifact.get("name"),
            "model_id": artifact.get("model_id"),
            "model_type": artifact.get("model_type"),
            "version": artifact.get("version"),
            "metrics": artifact.get("metrics", {}),
        },
        "accounts": accounts,
        "distribution": {"buckets": buckets, "total": len(accounts)},
    }


def _band(score: float) -> str:
    if score >= 0.8:
        return "very_high"
    if score >= 0.6:
        return "high"
    if score >= 0.4:
        return "medium"
    if score >= 0.2:
        return "low"
    return "very_low"


def require_model(artifact: dict | None) -> dict:
    if not artifact:
        raise ModelNotTrained("bot_detection")
    return artifact
