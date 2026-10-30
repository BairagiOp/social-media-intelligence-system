"""Misinformation classification (baseline: TF-IDF + Logistic Regression).

IMPORTANT: outputs are model classifications and confidence estimates only.
They are NOT factual determinations. Human verification is always required.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from app.utils.column_detect import resolve
from app.utils.errors import ModelNotTrained, ValidationFailed

logger = logging.getLogger(__name__)

DISCLAIMER = (
    "This is a model classification with a confidence estimate — not a "
    "factual determination that content is misinformation. Human verification "
    "against reliable sources is required before any conclusion is drawn."
)


def build_text_corpus(df: pd.DataFrame, mapping: dict) -> pd.Series:
    text_col = resolve(mapping, "text") or resolve(mapping, "text_clean")
    headline_col = resolve(mapping, "headline")
    parts = []
    if text_col and text_col in df.columns:
        parts.append(df[text_col].fillna("").astype(str))
    if headline_col and headline_col in df.columns:
        parts.append(df[headline_col].fillna("").astype(str))
    if not parts:
        raise ValidationFailed(
            "Misinformation analysis requires a text (or headline) column."
        )
    corpus = parts[0]
    for extra in parts[1:]:
        corpus = corpus + " " + extra
    return corpus


def predict_content(df: pd.DataFrame, mapping: dict, artifact: dict, limit: int = 500) -> dict:
    if not artifact:
        raise ModelNotTrained("misinformation")

    pipeline = artifact["model"]
    corpus = build_text_corpus(df, mapping)
    mask = corpus.str.strip().ne("")
    sub = df[mask].reset_index(drop=True)
    texts = corpus[mask].reset_index(drop=True)
    if texts.empty:
        raise ValidationFailed("No non-empty text rows to classify.")

    texts = texts.head(limit)
    sub = sub.head(limit)

    proba = pipeline.predict_proba(texts)
    classes = list(getattr(pipeline, "classes_", [0, 1]))
    flag_idx = classes.index(1) if 1 in classes else len(classes) - 1

    # Per-sample feature contributions from the linear model.
    try:
        tfidf = pipeline.named_steps["tfidf"]
        clf = pipeline.named_steps["clf"]
        coef = np.asarray(clf.coef_).reshape(-1)
        feature_names = tfidf.get_feature_names_out()
        X = tfidf.transform(texts)
    except Exception:  # pragma: no cover - non-pipeline artifact
        X, coef, feature_names = None, None, None

    text_col = resolve(mapping, "text") or resolve(mapping, "text_clean")
    user_col = resolve(mapping, "username")
    platform_col = resolve(mapping, "platform")
    ts_col = resolve(mapping, "timestamp")
    domain_col = resolve(mapping, "domain")

    items = []
    for i in range(len(texts)):
        p = float(proba[i, flag_idx])
        classification = "MODEL_FLAGGED" if p >= 0.5 else "NOT_FLAGGED"
        top_features = []
        if X is not None and coef is not None:
            row = X[i].toarray().ravel()
            contrib = row * coef
            order = np.argsort(np.abs(contrib))[::-1][:6]
            top_features = [
                {
                    "term": str(feature_names[j]),
                    "weight": round(float(contrib[j]), 5),
                    "tfidf": round(float(row[j]), 4),
                }
                for j in order
                if contrib[j] != 0
            ]
        item = {
            "text": str(texts.iloc[i])[:400],
            "classification": classification,
            "confidence": round(max(p, 1 - p), 4),
            "flag_probability": round(p, 4),
            "top_features": top_features,
        }
        if user_col:
            item["username"] = str(sub[user_col].iloc[i])
        if platform_col:
            item["platform"] = str(sub[platform_col].iloc[i])
        if ts_col and ts_col in sub.columns:
            item["timestamp"] = str(sub[ts_col].iloc[i])
        if domain_col:
            item["domain"] = str(sub[domain_col].iloc[i])
        items.append(item)

    flagged = [i for i in items if i["classification"] == "MODEL_FLAGGED"]
    mean_conf = (
        float(np.mean([i["confidence"] for i in items])) if items else 0.0
    )
    return {
        "disclaimer": DISCLAIMER,
        "model": {
            "name": artifact.get("name"),
            "model_id": artifact.get("model_id"),
            "model_type": artifact.get("model_type"),
            "version": artifact.get("version"),
            "metrics": artifact.get("metrics", {}),
        },
        "summary": {
            "evaluated": len(items),
            "model_flagged": len(flagged),
            "flagged_ratio": round(len(flagged) / len(items), 4) if items else 0.0,
            "mean_confidence": round(mean_conf, 4),
        },
        "items": items,
    }
