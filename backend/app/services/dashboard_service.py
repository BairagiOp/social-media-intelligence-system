"""Dashboard summary: every number is computed from real backend data."""
from __future__ import annotations

import logging
from collections import Counter, defaultdict

import pandas as pd

from app.analysis import bot as bot_analysis
from app.analysis import misinformation as misinfo_analysis
from app.analysis import sentiment as sentiment_analysis
from app.analysis import topics as topics_analysis
from app.app_state import analysis_cache
from app.ml import registry
from app.ml.trainer import TASKS
from app.services import dataset_service, evidence_service
from app.utils.column_detect import resolve

logger = logging.getLogger(__name__)


def _primary_dataset(db, dataset_id: str | None):
    datasets = dataset_service.list_datasets(db)
    if not datasets:
        return None, None
    if dataset_id:
        for d in datasets:
            if d.id == dataset_id:
                return d, dataset_service.dataset_frame(d)
        return None, None
    # Prefer a preprocessed dataset, else the most recent.
    datasets.sort(key=lambda d: (d.status != "PREPROCESSED",))
    chosen = datasets[0]
    return chosen, dataset_service.dataset_frame(chosen)


def _active_topic_k(db, default: int = 6) -> int:
    """Number of topics used by the active topic model, if one is registered."""
    record = registry.get_active(db, "topic_model")
    if record:
        k = record.metrics.get("n_topics")
        if k:
            return int(k)
    return default


def build_summary(db, dataset_id: str | None = None) -> dict:
    warnings: list[str] = []
    datasets = dataset_service.list_datasets(db)
    evidence_items = len(evidence_service.list_evidence(db, limit=1000))

    total_records = sum(d.records for d in datasets)
    active_datasets = len(datasets)

    dataset, df = _primary_dataset(db, dataset_id)
    if dataset is None:
        warnings.append("No dataset loaded. Upload a dataset or load the sample data.")

    mapping = dataset.column_map or {} if dataset else {}
    accounts = 0
    platform_distribution: dict = {}
    activity_timeline: list = []
    engagement_trend: list = []
    sentiment_timeline: list = []
    bot_distribution = None
    automated_likelihood = None
    topic_distribution: dict = {}
    topic_count = 0
    flagged_content = None

    if df is not None:
        user_col = resolve(mapping, "username") or resolve(mapping, "user_id")
        if user_col and user_col in df.columns:
            accounts = int(df[user_col].nunique())

        platform_col = resolve(mapping, "platform")
        if platform_col and platform_col in df.columns:
            platform_distribution = {
                str(k): int(v)
                for k, v in df[platform_col].value_counts().head(12).items()
            }

        ts_col = resolve(mapping, "timestamp")
        if ts_col and ts_col in df.columns:
            ts = pd.to_datetime(df[ts_col], utc=True, errors="coerce")
            by_day = ts.dt.strftime("%Y-%m-%d").value_counts().sort_index()
            activity_timeline = [
                {"date": d, "count": int(c)} for d, c in by_day.items()
            ]

            likes = pd.to_numeric(
                df[resolve(mapping, "likes")], errors="coerce"
            ) if resolve(mapping, "likes") in df.columns else 0
            comments = pd.to_numeric(
                df[resolve(mapping, "comments")], errors="coerce"
            ) if resolve(mapping, "comments") in df.columns else 0
            shares = pd.to_numeric(
                df[resolve(mapping, "shares")], errors="coerce"
            ) if resolve(mapping, "shares") in df.columns else 0
            engagement = (likes if not isinstance(likes, int) else 0) + \
                2 * (comments if not isinstance(comments, int) else 0) + \
                3 * (shares if not isinstance(shares, int) else 0)
            if not isinstance(engagement, int):
                daily = (
                    pd.DataFrame({"day": ts.dt.strftime("%Y-%m-%d"), "e": engagement})
                    .dropna()
                    .groupby("day")["e"]
                    .mean()
                    .round(2)
                )
                engagement_trend = [
                    {"date": d, "value": float(v)} for d, v in daily.items()
                ]

        # Sentiment timeline (VADER — always available)
        text_col = resolve(mapping, "text")
        if text_col and text_col in df.columns:
            try:
                cached = analysis_cache.get(dataset.id, "sentiment")
                if cached:
                    sentiment_timeline = cached.get("timeline", [])
                else:
                    result = sentiment_analysis.analyze_dataset(df, mapping)
                    analysis_cache.store(dataset.id, "sentiment", result)
                    sentiment_timeline = result.get("timeline", [])
            except Exception as exc:
                warnings.append(f"Sentiment analysis unavailable: {exc}")

        # Topics (fit if not cached)
        if text_col and text_col in df.columns:
            try:
                cached = analysis_cache.get(dataset.id, "topics")
                if not cached:
                    cached = topics_analysis.analyze_dataset(
                        df, mapping, n_topics=_active_topic_k(db)
                    )
                    analysis_cache.store(dataset.id, "topics", cached)
                topic_distribution = cached.get("distribution", {})
                topic_count = int(cached.get("n_topics", 0))
            except Exception as exc:
                warnings.append(f"Topic modeling unavailable: {exc}")

        # Bot likelihood (active model required — never faked)
        artifact = registry.active_artifact(db, "bot_detection")
        if artifact:
            try:
                cached = analysis_cache.get(dataset.id, "bot")
                if not cached:
                    features = bot_analysis.build_account_features(df, mapping)
                    cached = bot_analysis.predict_accounts(features, artifact)
                    analysis_cache.store(dataset.id, "bot", cached)
                bot_distribution = cached.get("distribution")
                scores = [a["score"] for a in cached.get("accounts", [])]
                automated_likelihood = {
                    "mean": round(sum(scores) / len(scores), 4) if scores else 0.0,
                    "high_risk": sum(1 for s in scores if s >= 0.6),
                    "total_accounts": len(scores),
                    "model_id": cached.get("model", {}).get("model_id"),
                }
            except Exception as exc:
                warnings.append(f"Automated-account analysis unavailable: {exc}")
        else:
            warnings.append("Model not trained: automated-account likelihood unavailable.")

        # Misinformation flags (active model required)
        artifact = registry.active_artifact(db, "misinformation")
        if artifact:
            try:
                cached = analysis_cache.get(dataset.id, "misinformation")
                if not cached:
                    cached = misinfo_analysis.predict_content(
                        df, mapping, artifact, limit=500
                    )
                    analysis_cache.store(dataset.id, "misinformation", cached)
                flagged_content = {
                    **cached.get("summary", {}),
                    "model_id": cached.get("model", {}).get("model_id"),
                }
            except Exception as exc:
                warnings.append(f"Misinformation analysis unavailable: {exc}")
        else:
            warnings.append("Model not trained: misinformation classification unavailable.")

    # Model accuracy from the registry (real evaluation metrics only)
    model_accuracy: dict = {}
    for task in TASKS:
        record = registry.get_active(db, task)
        if record:
            model_accuracy[task] = {
                "model_id": record.model_id,
                "name": record.name,
                "accuracy": record.metrics.get("accuracy"),
                "f1": record.metrics.get("f1"),
                "roc_auc": record.metrics.get("roc_auc"),
            }
        else:
            model_accuracy[task] = None
            if task != "topic_model":
                warnings.append(f"Model not trained: {task}")

    return {
        "dataset_id": dataset.id if dataset else None,
        "total_records": int(total_records),
        "active_datasets": active_datasets,
        "accounts_analyzed": accounts,
        "automated_likelihood": automated_likelihood,
        "flagged_content": flagged_content,
        "topic_count": topic_count,
        "evidence_items": evidence_items,
        "model_accuracy": model_accuracy,
        "activity_timeline": activity_timeline,
        "sentiment_timeline": sentiment_timeline,
        "platform_distribution": platform_distribution,
        "bot_distribution": bot_distribution,
        "topic_distribution": topic_distribution,
        "engagement_trend": engagement_trend,
        "warnings": warnings,
    }
