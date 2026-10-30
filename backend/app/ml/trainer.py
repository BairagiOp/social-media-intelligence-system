"""Training pipelines for every supported ML task.

All metrics are computed from real train/test evaluation — nothing here is
hard-coded or fabricated.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression, SGDClassifier
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline
from sklearn.decomposition import NMF

from app.analysis.bot import FEATURE_COLUMNS, build_account_features
from app.ml import registry
from app.models.model_registry import ModelRecord
from app.security.audit import record_event
from app.services import dataset_service
from app.utils.column_detect import resolve
from app.utils.errors import TrainingError, ValidationFailed
from app.utils.text_cleaning import clean_text

logger = logging.getLogger(__name__)

TASKS: dict[str, dict] = {
    "sentiment": {
        "label": "Sentiment Classification",
        "requires_target": True,
        "target_candidates": ["label", "sentiment", "sentiment_label"],
        "text_based": True,
        "models": [
            {"id": "logistic_regression", "label": "Logistic Regression (TF-IDF)"},
            {"id": "multinomial_nb", "label": "Multinomial Naive Bayes (TF-IDF)"},
            {"id": "random_forest", "label": "Random Forest (TF-IDF)"},
        ],
    },
    "bot_detection": {
        "label": "Automated-Account Detection",
        "requires_target": True,
        "target_candidates": ["is_automated", "is_bot", "bot_label"],
        "text_based": False,
        "feature_candidates": FEATURE_COLUMNS,
        "models": [
            {"id": "logistic_regression", "label": "Logistic Regression"},
            {"id": "random_forest", "label": "Random Forest"},
            {"id": "gradient_boosting", "label": "Gradient Boosting"},
        ],
    },
    "misinformation": {
        "label": "Misinformation Classification",
        "requires_target": True,
        "target_candidates": ["misinfo_label", "is_fake", "label"],
        "text_based": True,
        "models": [
            {"id": "logistic_regression", "label": "Logistic Regression (TF-IDF) — baseline"},
            {"id": "multinomial_nb", "label": "Multinomial Naive Bayes (TF-IDF)"},
        ],
    },
    "topic_model": {
        "label": "Topic Modeling (TF-IDF + NMF)",
        "requires_target": False,
        "target_candidates": [],
        "text_based": True,
        "models": [{"id": "nmf", "label": "Non-negative Matrix Factorization"}],
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def classification_metrics(y_true, y_pred, y_proba=None, classes=None) -> dict:
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    binary = len(set(y_true.tolist()) | set(y_pred.tolist())) == 2
    average = "binary" if binary else "weighted"

    metrics = {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "precision": round(float(precision_score(y_true, y_pred, average=average, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, y_pred, average=average, zero_division=0)), 4),
        "f1": round(float(f1_score(y_true, y_pred, average=average, zero_division=0)), 4),
        "roc_auc": None,
        "confusion_matrix": confusion_matrix(y_true, y_pred).tolist(),
        "classes": [str(c) for c in (classes if classes is not None else sorted(set(y_true.tolist())))],
        "report": classification_report(y_true, y_pred, zero_division=0, output_dict=True),
        "average": average,
    }
    if y_proba is not None:
        try:
            if binary:
                proba = y_proba
                if proba.ndim == 2 and proba.shape[1] == 2:
                    proba = proba[:, 1]
                metrics["roc_auc"] = round(
                    float(roc_auc_score(y_true, proba)), 4
                )
            else:
                metrics["roc_auc"] = round(
                    float(roc_auc_score(y_true, y_proba, multi_class="ovr")), 4
                )
        except Exception:
            metrics["roc_auc"] = None
    return metrics


def _ensure_text_clean(df: pd.DataFrame, mapping: dict) -> str:
    """Return the name of a cleaned-text column, creating one if needed."""
    if "text_clean" in df.columns:
        return "text_clean"
    text_col = resolve(mapping, "text")
    if not text_col or text_col not in df.columns:
        raise ValidationFailed("No text column found for text-based training.")
    df["text_clean"] = [clean_text(t) for t in df[text_col].fillna("")]
    return "text_clean"


def _coerce_binary(series: pd.Series) -> tuple[pd.Series, list[str] | None]:
    """Coerce arbitrary labels into {0,1} (or return class names for multiclass)."""
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().all() and set(numeric.dropna().unique()) <= {0, 1}:
        return numeric.astype(int), None
    if series.dtype == bool:
        return series.astype(int), None
    values = sorted(str(v) for v in series.dropna().unique())
    if len(values) == 2:
        mapping = {values[0]: 0, values[1]: 1}
        return series.map(mapping).astype(int), values
    return series.astype(str), None


def _build_estimator(model_type: str, seed: int = 42):
    if model_type == "logistic_regression":
        return LogisticRegression(max_iter=1000, random_state=seed)
    if model_type == "random_forest":
        return RandomForestClassifier(
            n_estimators=200, random_state=seed, n_jobs=-1, class_weight="balanced"
        )
    if model_type == "gradient_boosting":
        return GradientBoostingClassifier(random_state=seed, n_estimators=150)
    if model_type == "multinomial_nb":
        return MultinomialNB()
    if model_type == "linear_svm":
        return SGDClassifier(loss="hinge", random_state=seed, max_iter=1000)
    raise TrainingError(f"Unknown model type '{model_type}'.")


def _split(X, y, test_size: float, seed: int = 42):
    y = pd.Series(y)
    if len(X) < 40:
        raise TrainingError(
            f"Insufficient training data: {len(X)} rows (need at least 40)."
        )
    counts = y.value_counts()
    if counts.min() < 2:
        raise TrainingError(
            "A target class has fewer than 2 samples — cannot stratify the split."
        )
    stratify = y if counts.min() >= 5 else None
    try:
        X_train, X_test, y_train, y_test = train_test_split(
            list(X), list(y), test_size=test_size, random_state=seed, stratify=stratify
        )
    except ValueError as exc:
        raise TrainingError(f"Train/test split failed: {exc}") from exc
    return X_train, X_test, y_train, y_test


def _attach_target(
    features: pd.DataFrame, df: pd.DataFrame, mapping: dict, target: str
) -> pd.DataFrame:
    """Join an arbitrary dataset target column onto account-level features."""
    if target in features.columns:
        return features
    user_col = resolve(mapping, "username") or resolve(mapping, "user_id")
    if target not in df.columns or not user_col:
        raise TrainingError(f"Target column '{target}' not found in dataset.")
    labels = df[target].groupby(df[user_col]).first()
    merged = features.copy()
    merged[target] = merged["username"].map(labels)
    return merged


# ---------------------------------------------------------------------------
# Task trainers
# ---------------------------------------------------------------------------

def train_sentiment(db, job, params) -> ModelRecord:
    dataset = dataset_service.get_dataset(db, params["dataset_id"])
    df = dataset_service.dataset_frame(dataset)
    mapping = dataset.column_map or {}

    job.step("preprocess", 15, "Cleaning text column")
    clean_col = _ensure_text_clean(df, mapping)

    target = params.get("target") or "label"
    if target not in df.columns:
        raise TrainingError(f"Target column '{target}' not found in dataset.")
    df = df[df[target].notna()].reset_index(drop=True)

    texts = df[clean_col].astype(str)
    labels = df[target].astype(str)
    if labels.nunique() < 2:
        raise TrainingError("Target column must contain at least 2 classes.")

    job.step("split", 35, "Splitting data")
    X_train, X_test, y_train, y_test = _split(
        texts, labels, params.get("test_size", 0.2)
    )

    model_type = params.get("model_type", "logistic_regression")
    pipeline = Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(
                    max_features=params.get("max_features", 5000),
                    ngram_range=(1, 2),
                    stop_words="english",
                    sublinear_tf=True,
                ),
            ),
            ("clf", _build_estimator(model_type)),
        ]
    )

    job.step("train", 55, f"Training {model_type}")
    pipeline.fit(X_train, y_train)

    job.step("evaluate", 80, "Computing metrics")
    y_pred = pipeline.predict(X_test)
    y_proba = None
    if hasattr(pipeline.named_steps["clf"], "predict_proba"):
        try:
            y_proba = pipeline.predict_proba(X_test)
        except Exception:
            y_proba = None
    metrics = classification_metrics(
        y_test, y_pred, y_proba, classes=sorted(labels.unique())
    )
    metrics["train_size"] = len(X_train)
    metrics["test_size"] = len(X_test)
    metrics["model_type"] = model_type

    job.step("save", 92, "Serializing model")
    artifact = {
        "model": pipeline,
        "features": ["text"],
        "model_type": model_type,
        "target": target,
        "params": {k: v for k, v in params.items() if k != "target"},
    }
    record = registry.create_record(
        db,
        name=params.get("name") or f"Sentiment {model_type}",
        task="sentiment",
        dataset_id=dataset.id,
        model_type=model_type,
        metrics=metrics,
        features=["text"],
        artifact=artifact,
    )
    _audit_model(db, dataset, record, metrics)
    return record


def train_misinformation(db, job, params) -> ModelRecord:
    dataset = dataset_service.get_dataset(db, params["dataset_id"])
    df = dataset_service.dataset_frame(dataset)
    mapping = dataset.column_map or {}

    job.step("preprocess", 15, "Building text corpus")
    clean_col = _ensure_text_clean(df, mapping)

    target = params.get("target") or "misinfo_label"
    if target not in df.columns:
        raise TrainingError(f"Target column '{target}' not found in dataset.")

    headline_col = resolve(mapping, "headline")
    work = df[df[target].notna()].reset_index(drop=True)
    corpus = work[clean_col].astype(str)
    if headline_col and headline_col in work.columns:
        corpus = corpus + " " + work[headline_col].fillna("").astype(str)

    y, class_names = _coerce_binary(work[target])
    keep = y.notna()
    corpus, y = corpus[keep], y[keep]
    if y.nunique() < 2:
        raise TrainingError("Misinformation target must contain 2 classes.")

    job.step("split", 35, "Splitting data")
    X_train, X_test, y_train, y_test = _split(corpus, y, params.get("test_size", 0.2))

    model_type = params.get("model_type", "logistic_regression")
    pipeline = Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(
                    max_features=params.get("max_features", 5000),
                    ngram_range=(1, 2),
                    stop_words="english",
                    sublinear_tf=True,
                ),
            ),
            ("clf", _build_estimator(model_type)),
        ]
    )

    job.step("train", 55, f"Training {model_type}")
    pipeline.fit(X_train, y_train)

    job.step("evaluate", 80, "Computing metrics")
    y_pred = pipeline.predict(X_test)
    y_proba = None
    if hasattr(pipeline.named_steps["clf"], "predict_proba"):
        try:
            y_proba = pipeline.predict_proba(X_test)
        except Exception:
            y_proba = None
    metrics = classification_metrics(
        y_test, y_pred, y_proba,
        classes=class_names if class_names else [0, 1],
    )
    metrics["train_size"] = len(X_train)
    metrics["test_size"] = len(X_test)
    metrics["model_type"] = model_type
    metrics["class_names"] = class_names or [0, 1]

    job.step("save", 92, "Serializing model")
    artifact = {
        "model": pipeline,
        "features": ["text", "headline"] if headline_col else ["text"],
        "model_type": model_type,
        "target": target,
    }
    record = registry.create_record(
        db,
        name=params.get("name") or f"Misinfo {model_type}",
        task="misinformation",
        dataset_id=dataset.id,
        model_type=model_type,
        metrics=metrics,
        features=artifact["features"],
        artifact=artifact,
    )
    _audit_model(db, dataset, record, metrics)
    return record


def train_bot_detection(db, job, params) -> ModelRecord:
    dataset = dataset_service.get_dataset(db, params["dataset_id"])
    df = dataset_service.dataset_frame(dataset)
    mapping = dataset.column_map or {}

    job.step("preprocess", 15, "Engineering account-level features")
    features = build_account_features(df, mapping)
    target = params.get("target") or "is_automated"
    features = _attach_target(features, df, mapping, target)
    if target not in features.columns:
        raise TrainingError(
            f"Target column '{target}' not found (need an account-level label "
            "such as is_automated)."
        )

    features = features[features[target].notna()].reset_index(drop=True)
    y, class_names = _coerce_binary(features[target])
    selected = params.get("features") or [
        c for c in FEATURE_COLUMNS if c in features.columns
    ]
    selected = [c for c in selected if c in features.columns]
    if not selected:
        raise TrainingError("No usable feature columns were selected.")

    X = features[selected].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    if y.nunique() < 2:
        raise TrainingError("Target must contain both classes (e.g. bot vs human).")

    job.step("split", 35, "Splitting data")
    y_all = y.tolist()
    y_counts = pd.Series(y_all).value_counts()
    if len(y_all) < 40:
        raise TrainingError(
            f"Insufficient training data: {len(y_all)} accounts (need at least 40)."
        )
    if y_counts.min() < 2:
        raise TrainingError(
            "A target class has fewer than 2 samples — cannot stratify the split."
        )
    X_all = X.values.tolist()
    from sklearn.model_selection import train_test_split as _tts

    idx_train, idx_test = _tts(
        np.arange(len(y_all)),
        test_size=params.get("test_size", 0.2),
        random_state=42,
        stratify=y_all if y_counts.min() >= 5 else None,
    )
    X_train = np.asarray([X_all[i] for i in idx_train])
    X_test = np.asarray([X_all[i] for i in idx_test])
    y_train = [y_all[i] for i in idx_train]
    y_test = [y_all[i] for i in idx_test]

    model_type = params.get("model_type", "random_forest")
    job.step("train", 55, f"Training {model_type}")
    clf = _build_estimator(model_type)
    clf.fit(X_train, y_train)

    job.step("evaluate", 80, "Computing metrics")
    y_pred = clf.predict(X_test)
    y_proba = None
    if hasattr(clf, "predict_proba"):
        try:
            y_proba = clf.predict_proba(X_test)
        except Exception:
            y_proba = None
    metrics = classification_metrics(y_test, y_pred, y_proba)
    metrics["train_size"] = len(X_train)
    metrics["test_size"] = len(X_test)
    metrics["model_type"] = model_type
    metrics["features"] = selected
    metrics["class_names"] = class_names or [0, 1]
    metrics["accounts"] = int(len(features))

    if hasattr(clf, "feature_importances_"):
        metrics["feature_importance"] = {
            f: round(float(v), 5)
            for f, v in zip(selected, clf.feature_importances_)
        }
    elif hasattr(clf, "coef_"):
        coef = np.asarray(clf.coef_).reshape(-1)[: len(selected)]
        metrics["feature_importance"] = {
            f: round(float(v), 5) for f, v in zip(selected, coef)
        }

    job.step("save", 92, "Serializing model")
    artifact = {
        "model": clf,
        "features": selected,
        "model_type": model_type,
        "target": target,
        "feature_stats": {
            "mean": X.mean().tolist(),
            "std": X.std().replace(0, 1).tolist(),
        },
    }
    record = registry.create_record(
        db,
        name=params.get("name") or f"Bot {model_type}",
        task="bot_detection",
        dataset_id=dataset.id,
        model_type=model_type,
        metrics=metrics,
        features=selected,
        artifact=artifact,
    )
    _audit_model(db, dataset, record, metrics)
    return record


def train_topics(db, job, params) -> ModelRecord:
    dataset = dataset_service.get_dataset(db, params["dataset_id"])
    df = dataset_service.dataset_frame(dataset)
    mapping = dataset.column_map or {}

    job.step("preprocess", 15, "Vectorizing corpus")
    clean_col = _ensure_text_clean(df, mapping)
    texts = df[clean_col].fillna("").astype(str)
    texts = texts[texts.str.strip().ne("")]
    if len(texts) < 10:
        raise TrainingError("Insufficient text records for topic modeling (need ≥ 10).")

    n_topics = int(params.get("n_topics", 6))
    vectorizer = TfidfVectorizer(
        max_features=params.get("max_features", 5000),
        stop_words="english",
        ngram_range=(1, 2),
        min_df=2,
        max_df=0.9,
        sublinear_tf=True,
    )
    job.step("train", 45, f"Fitting TF-IDF + NMF ({n_topics} topics)")
    tfidf = vectorizer.fit_transform(texts.tolist())
    n_topics = max(2, min(n_topics, 20, tfidf.shape[0]))
    model = NMF(
        n_components=n_topics, init="nndsvda", random_state=42, max_iter=400
    )
    W = model.fit_transform(tfidf)

    job.step("evaluate", 80, "Computing topic quality metrics")
    doc_strength = W.max(axis=1)
    metrics = {
        "n_topics": n_topics,
        "documents": int(len(texts)),
        "reconstruction_error": round(float(model.reconstruction_err_), 4),
        "mean_document_topic_strength": round(float(np.mean(doc_strength)), 4),
        "vocabulary_size": int(tfidf.shape[1]),
        "note": "Unsupervised model — no accuracy metrics. Quality indicators shown.",
    }
    terms = vectorizer.get_feature_names_out()
    metrics["top_keywords"] = {
        str(t): [
            str(terms[i])
            for i in model.components_[t].argsort()[::-1][:8]
        ]
        for t in range(n_topics)
    }

    job.step("save", 92, "Serializing model")
    artifact = {
        "model": {"vectorizer": vectorizer, "nmf": model},
        "features": ["text"],
        "model_type": "nmf",
        "target": None,
    }
    record = registry.create_record(
        db,
        name=params.get("name") or f"Topics NMF k={n_topics}",
        task="topic_model",
        dataset_id=dataset.id,
        model_type="nmf",
        metrics=metrics,
        features=["text"],
        artifact=artifact,
    )
    _audit_model(db, dataset, record, metrics)
    return record


TRAINERS = {
    "sentiment": train_sentiment,
    "misinformation": train_misinformation,
    "bot_detection": train_bot_detection,
    "topic_model": train_topics,
}


def _audit_model(db, dataset, record: ModelRecord, metrics: dict) -> None:
    if dataset.evidence_id:
        record_event(
            db,
            dataset.evidence_id,
            "MODEL",
            {
                "model_id": record.model_id,
                "task": record.task,
                "accuracy": metrics.get("accuracy"),
                "f1": metrics.get("f1"),
                "roc_auc": metrics.get("roc_auc"),
                "dataset_id": dataset.id,
                "trained_at": datetime.now(timezone.utc).isoformat(),
            },
        )


def run_training(db, job, params: dict) -> ModelRecord:
    task = params.get("task")
    if task not in TRAINERS:
        raise TrainingError(f"Unknown ML task '{task}'.")
    start = time.time()
    job.step("validate", 5, "Loading dataset")
    record = TRAINERS[task](db, job, params)
    job.step("complete", 100, f"Finished in {time.time() - start:.1f}s")
    return record
