"""Analysis engine tests: sentiment, topics, network, bot, misinformation."""
from __future__ import annotations

import io

import pandas as pd
import pytest

from app.analysis.sentiment import label_for_compound, score_texts, vader_labels
from app.analysis.topics import analyze_dataset as topics_analyze
from app.analysis.bot import build_account_features
from app.utils.errors import ModelNotTrained


def test_vader_scores():
    results = score_texts(
        ["I absolutely love this, fantastic work!", "This is horrible and disappointing."]
    )
    assert results[0]["compound"] > 0.05
    assert results[1]["compound"] < -0.05
    assert set(results[0]) == {"positive", "negative", "neutral", "compound"}


def test_vader_labels():
    labels = vader_labels(["great amazing wonderful", "awful terrible worst"])
    assert labels[0] == "positive"
    assert labels[1] == "negative"
    assert label_for_compound(0.0) == "neutral"


def test_sentiment_endpoint(client, uploaded_dataset):
    resp = client.post(
        "/api/analysis/sentiment", json={"dataset_id": uploaded_dataset["id"]}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 120
    assert "intent" in body["disclaimer"].lower()
    ratios = body["overall"]["ratios"]
    assert abs(sum(ratios.values()) - 1.0) < 0.01
    assert len(body["timeline"]) >= 1
    assert body["most_positive"] and body["most_negative"]


def test_topics_endpoint(client, uploaded_dataset):
    resp = client.post(
        "/api/analysis/topics",
        json={"dataset_id": uploaded_dataset["id"], "n_topics": 4, "top_terms": 6},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["n_topics"] == 4
    assert len(body["topics"]) == 4
    for topic in body["topics"]:
        assert len(topic["keywords"]) <= 6
        assert topic["keywords"][0]["term"]
        assert "frequency" in topic
    assert body["quality"]["documents"] == 120


def test_topics_insufficient_data(client, uploaded_dataset):
    tiny = "id,text\n" + "".join(f'{i},"hi{i}"\n' for i in range(5))
    resp = client.post(
        "/api/datasets/upload",
        files={"file": ("tiny.csv", io.BytesIO(tiny.encode()), "text/csv")},
    )
    tiny_id = resp.json()["id"]
    resp2 = client.post(
        "/api/analysis/topics", json={"dataset_id": tiny_id, "n_topics": 4}
    )
    assert resp2.status_code == 422
    assert "Insufficient" in resp2.json()["detail"]


def test_bot_model_not_trained_yet(client, uploaded_dataset):
    """Before any training, the API must say 'Model not trained' — not invent scores."""
    resp = client.post(
        "/api/analysis/bot", json={"dataset_id": uploaded_dataset["id"]}
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["code"] == "model_not_trained"
    assert "Model not trained" in body["detail"]


def test_misinformation_model_not_trained_yet(client, uploaded_dataset):
    resp = client.post(
        "/api/analysis/misinformation",
        json={"dataset_id": uploaded_dataset["id"]},
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "model_not_trained"


def test_bot_require_model_helper():
    with pytest.raises(ModelNotTrained):
        require = ModelNotTrained("bot_detection")
        raise require


def test_build_account_features(uploaded_dataset):
    from app.services import dataset_service
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        dataset = dataset_service.get_dataset(db, uploaded_dataset["id"])
        df = dataset_service.dataset_frame(dataset)
        features = build_account_features(df, dataset.column_map)
    finally:
        db.close()

    assert len(features) == 40
    for col in (
        "followers", "following", "post_count", "posting_frequency",
        "avg_interval_hours", "avg_text_length", "dup_content_ratio",
        "engagement_ratio", "activity_regularity", "account_age",
    ):
        assert col in features.columns
    assert "label" in features.columns
    assert features["label"].isin([0, 1]).all()


def test_network_graph_endpoint(client, uploaded_dataset):
    resp = client.get(
        "/api/network/graph",
        params={"dataset_id": uploaded_dataset["id"], "min_weight": 1},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["stats"]["nodes"] >= 2
    assert body["stats"]["edges"] >= 1
    assert body["communities"]["count"] >= 1
    assert "centrality" in body
    assert "coordination" in body["disclaimer"].lower()
    node_ids = {n["id"] for n in body["nodes"]}
    for edge in body["edges"]:
        assert edge["source"] in node_ids
        assert edge["target"] in node_ids


def test_topics_fit_helper():
    texts = [
        "climate change renewable energy solar power grid",
        "football match scores championship league",
        "movie release box office actor interview",
    ] * 12
    from app.analysis.topics import fit_topics

    vectorizer, model, tfidf, W = fit_topics(texts, n_topics=3)
    assert W.shape[0] == len(texts)
    assert W.shape[1] == 3
    assert len(vectorizer.get_feature_names_out()) > 0
