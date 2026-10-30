"""End-to-end ML tests: training, metrics, registry, inference, reports."""
from __future__ import annotations

import time

import pytest

from app.database import SessionLocal
from app.ml import registry
from app.ml.trainer import run_training


class DummyJob:
    def __init__(self):
        self.steps = []

    def step(self, name, progress, detail=""):
        self.steps.append((name, progress))


def _train(task, dataset_id, **extra):
    db = SessionLocal()
    try:
        record = run_training(
            db, DummyJob(), {"task": task, "dataset_id": dataset_id, **extra}
        )
        registry.activate(db, record.model_id)
        return record
    finally:
        db.close()


@pytest.fixture(scope="module")
def trained_models(request):
    """Train all tasks once against a fresh dataset (module-scoped)."""
    import io

    from tests.conftest import make_sample_csv

    # client fixture is session-scoped; reuse via request.getfixturevalue
    client = request.getfixturevalue("client")
    csv_bytes = make_sample_csv(240)
    resp = client.post(
        "/api/datasets/upload",
        files={"file": ("ml_dataset.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert resp.status_code == 201, resp.text
    dataset_id = resp.json()["id"]

    records = {
        "sentiment": _train(
            "sentiment", dataset_id, target="label",
            model_type="logistic_regression",
        ),
        "bot_detection": _train(
            "bot_detection", dataset_id, target="is_automated",
            model_type="logistic_regression",
        ),
        "misinformation": _train(
            "misinformation", dataset_id, target="misinfo_label",
            model_type="logistic_regression",
        ),
        "topic_model": _train("topic_model", dataset_id, n_topics=4),
    }
    return {"dataset_id": dataset_id, "records": records}


def test_sentiment_training_metrics_are_real(trained_models):
    record = trained_models["records"]["sentiment"]
    m = record.metrics
    assert record.status == "TRAINED" or record.status == "ACTIVE"
    assert 0.0 <= m["accuracy"] <= 1.0
    assert 0.0 <= m["f1"] <= 1.0
    assert m["train_size"] + m["test_size"] == 240
    assert len(m["confusion_matrix"]) == 3  # pos/neu/neg
    # templates are separable — but the number must come from evaluation
    assert m["accuracy"] > 0.3


def test_bot_training_metrics(trained_models):
    m = trained_models["records"]["bot_detection"].metrics
    assert 0.0 <= m["accuracy"] <= 1.0
    assert m["roc_auc"] is None or 0.0 <= m["roc_auc"] <= 1.0
    assert "feature_importance" in m
    assert m["accounts"] == 40  # 240 rows / 20 users


def test_misinformation_training_metrics(trained_models):
    m = trained_models["records"]["misinformation"].metrics
    assert 0.0 <= m["accuracy"] <= 1.0
    assert m["test_size"] > 0


def test_topic_training(trained_models):
    m = trained_models["records"]["topic_model"].metrics
    assert m["n_topics"] == 4
    assert "reconstruction_error" in m
    assert "accuracy" not in m  # unsupervised — never faked


def test_model_registry_lists_and_active(trained_models, client):
    resp = client.get("/api/ml/models")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) >= 4
    active = client.get("/api/ml/active").json()
    assert active["sentiment"] is not None
    assert active["bot_detection"] is not None


def test_bot_inference_with_trained_model(client, trained_models):
    resp = client.post(
        "/api/analysis/bot", json={"dataset_id": trained_models["dataset_id"]}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["accounts"]) == 40
    for acc in body["accounts"]:
        assert 0.0 <= acc["score"] <= 1.0
        assert acc["classification"] in {"LIKELY_AUTOMATED", "LIKELY_HUMAN"}
        assert acc["feature_contributions"]
    assert "not proof" in body["disclaimer"].lower()


def test_misinformation_inference_with_trained_model(client, trained_models):
    resp = client.post(
        "/api/analysis/misinformation",
        json={"dataset_id": trained_models["dataset_id"], "limit": 50},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["summary"]["evaluated"] > 0
    assert "not a factual determination" in body["disclaimer"]
    for item in body["items"]:
        assert item["classification"] in {"MODEL_FLAGGED", "NOT_FLAGGED"}
        assert 0.0 <= item["confidence"] <= 1.0


def test_adhoc_sentiment_inference(client, trained_models):
    resp = client.post(
        "/api/analysis/inference",
        json={
            "task": "sentiment",
            "texts": ["I love this wonderful product", "This is awful"],
        },
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert items[0]["model_classification"] == "positive"
    assert items[1]["model_classification"] == "negative"


def test_training_job_via_api(client, trained_models):
    resp = client.post(
        "/api/ml/train",
        json={
            "dataset_id": trained_models["dataset_id"],
            "task": "sentiment",
            "target": "label",
            "model_type": "multinomial_nb",
        },
    )
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["job_id"]

    deadline = time.time() + 120
    body = None
    while time.time() < deadline:
        body = client.get(f"/api/ml/jobs/{job_id}").json()
        if body["status"] in {"COMPLETE", "FAILED"}:
            break
        time.sleep(0.5)

    assert body is not None
    assert body["status"] == "COMPLETE", body.get("error")
    assert body["result"]["model"]["metrics"]["accuracy"] >= 0.0
    assert body["progress"] == 100


def test_train_missing_target_column(client, trained_models):
    resp = client.post(
        "/api/ml/train",
        json={
            "dataset_id": trained_models["dataset_id"],
            "task": "sentiment",
            "target": "no_such_column",
        },
    )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]
    deadline = time.time() + 60
    body = None
    while time.time() < deadline:
        body = client.get(f"/api/ml/jobs/{job_id}").json()
        if body["status"] in {"COMPLETE", "FAILED"}:
            break
        time.sleep(0.5)
    assert body["status"] == "FAILED"
    assert "not found" in body["error"].lower()


def test_model_activate_archive_flow(client, trained_models):
    models = client.get("/api/ml/models", params={"task": "sentiment"}).json()["items"]
    assert models
    newest = models[0]
    resp = client.post(f"/api/ml/models/{newest['model_id']}/archive")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ARCHIVED"
    # reactivate
    resp = client.post(f"/api/ml/models/{newest['model_id']}/activate")
    assert resp.json()["status"] == "ACTIVE"


def test_report_generation(client, trained_models):
    resp = client.post(
        "/api/reports",
        json={"dataset_id": trained_models["dataset_id"], "title": "Test Intel Report"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    sections = body["content"]
    for key in (
        "executive_summary", "dataset_information", "evidence_integrity",
        "data_statistics", "sentiment_analysis", "topic_analysis",
        "automated_account_analysis", "misinformation_model_results",
        "network_analysis", "important_patterns", "model_performance",
        "limitations", "audit_trail",
    ):
        assert key in sections, f"missing section {key}"
        assert sections[key]["evidence_class"] in {
            "OBSERVED", "MODEL OUTPUT", "INFERENCE", "HUMAN"
        }
    assert "Human verification" in body["markdown"] or "human" in body["markdown"].lower()

    listing = client.get("/api/reports").json()
    assert listing["total"] >= 1


def test_dashboard_summary(client, trained_models):
    resp = client.get(
        "/api/dashboard/summary",
        params={"dataset_id": trained_models["dataset_id"]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_records"] > 0
    assert body["active_datasets"] >= 1
    assert body["accounts_analyzed"] == 40
    assert body["topic_count"] == 4
    assert body["evidence_items"] >= 1
    assert body["activity_timeline"]
    assert body["sentiment_timeline"]
    assert body["automated_likelihood"] is not None
    assert body["flagged_content"] is not None
    # accuracy must be real metrics from the registry
    sent = body["model_accuracy"]["sentiment"]
    assert sent and 0 <= sent["accuracy"] <= 1
