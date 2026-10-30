"""TF-IDF + NMF topic modeling."""
from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd
from sklearn.decomposition import NMF
from sklearn.feature_extraction.text import TfidfVectorizer

from app.utils.column_detect import resolve
from app.utils.errors import ValidationFailed

MAX_FEATURES = 5000


def fit_topics(
    texts: list[str],
    n_topics: int = 6,
    max_features: int = MAX_FEATURES,
    top_terms: int = 10,
):
    """Fit TF-IDF + NMF and return (vectorizer, nmf_model, tfidf_matrix)."""
    cleaned = [str(t) for t in texts if t and str(t).strip()]
    if len(cleaned) < max(10, n_topics):
        raise ValidationFailed(
            f"Insufficient text data for topic modeling (need at least "
            f"{max(10, n_topics)} non-empty records)."
        )
    vectorizer = TfidfVectorizer(
        max_features=max_features,
        stop_words="english",
        ngram_range=(1, 2),
        min_df=2,
        max_df=0.9,
        sublinear_tf=True,
    )
    try:
        tfidf = vectorizer.fit_transform(cleaned)
    except ValueError as exc:
        raise ValidationFailed(f"TF-IDF vectorization failed: {exc}") from exc

    n_topics = max(2, min(int(n_topics), 20, tfidf.shape[0]))
    model = NMF(
        n_components=n_topics,
        init="nndsvda",
        random_state=42,
        max_iter=400,
        beta_loss="frobenius",
    )
    W = model.fit_transform(tfidf)
    return vectorizer, model, tfidf, W


def _topic_keywords(vectorizer, model, topic_idx: int, top_terms: int) -> list[dict]:
    terms = np.array(vectorizer.get_feature_names_out())
    weights = model.components_[topic_idx]
    order = weights.argsort()[::-1][:top_terms]
    return [
        {"term": str(terms[i]), "weight": round(float(weights[i]), 5)}
        for i in order
    ]


def analyze_dataset(
    df: pd.DataFrame,
    mapping: dict,
    n_topics: int = 6,
    top_terms: int = 10,
) -> dict:
    text_col = (
        resolve(mapping, "text_clean")
        or resolve(mapping, "text")
    )
    if not text_col or text_col not in df.columns:
        raise ValidationFailed("No text column available for topic modeling.")

    raw_col = resolve(mapping, "text") or text_col
    texts = df[text_col].fillna("").astype(str)
    keep = [bool(t.strip()) for t in texts]
    sub = df[keep].reset_index(drop=True)
    texts = texts[keep].reset_index(drop=True)
    if len(texts) < 10:
        raise ValidationFailed("Insufficient records for topic modeling (need ≥ 10).")

    vectorizer, model, tfidf, W = fit_topics(texts.tolist(), n_topics=n_topics, top_terms=top_terms)
    n_topics = model.n_components

    doc_topics = W.argmax(axis=1)
    doc_strength = W.max(axis=1)

    ts_col = resolve(mapping, "timestamp")
    ts = (
        pd.to_datetime(sub[ts_col], utc=True, errors="coerce")
        if ts_col and ts_col in sub.columns
        else pd.Series([pd.NaT] * len(sub))
    )
    raw_texts = sub[raw_col].fillna("").astype(str) if raw_col in sub.columns else texts

    topics = []
    for tidx in range(n_topics):
        members = np.where(doc_topics == tidx)[0]
        freq = len(members)
        # Representative posts = strongest membership scores
        if freq:
            ranked = members[np.argsort(doc_strength[members])[::-1][:5]]
            representative = [
                {
                    "text": str(raw_texts.iloc[i])[:400],
                    "strength": round(float(doc_strength[i]), 4),
                }
                for i in ranked
            ]
        else:
            representative = []

        trend_map: dict[str, int] = defaultdict(int)
        for i in members:
            d = ts.iloc[i]
            if pd.notna(d):
                trend_map[d.strftime("%Y-%m-%d")] += 1
        trend = [{"date": d, "count": c} for d, c in sorted(trend_map.items())]

        topics.append(
            {
                "id": tidx,
                "keywords": _topic_keywords(vectorizer, model, tidx, top_terms),
                "representative": representative,
                "frequency": int(freq),
                "share": round(freq / len(texts), 4),
                "trend": trend,
            }
        )

    # Coherence-adjacent quality metric: mean max membership (document-topic confidence)
    quality = {
        "mean_document_topic_strength": round(float(np.mean(doc_strength)), 4),
        "reconstruction_error": round(float(model.reconstruction_err_), 4),
        "documents": int(len(texts)),
        "n_topics": int(n_topics),
    }

    # Topic co-occurrence (relationship visualization): how often topic pairs
    # appear among posts by the same author.
    user_col = resolve(mapping, "username")
    relations = []
    if user_col and user_col in sub.columns:
        pairs: dict[tuple[int, int], int] = defaultdict(int)
        tmp = pd.DataFrame({user_col: sub[user_col].fillna("unknown"), "topic": doc_topics})
        for _, group in tmp.groupby(user_col):
            tops = sorted(set(group["topic"].tolist()))
            for i in range(len(tops)):
                for j in range(i + 1, len(tops)):
                    pairs[(tops[i], tops[j])] += 1
        relations = [
            {"source": a, "target": b, "weight": w}
            for (a, b), w in sorted(pairs.items(), key=lambda kv: -kv[1])[:40]
        ]

    distribution = {str(t["id"]): t["frequency"] for t in topics}

    return {
        "n_topics": int(n_topics),
        "topics": topics,
        "distribution": distribution,
        "relations": relations,
        "quality": quality,
    }
