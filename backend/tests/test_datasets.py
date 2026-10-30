"""Dataset upload / validation / profile / preprocessing / explorer tests."""
from __future__ import annotations

import io


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in {"ok", "degraded"}
    assert body["database"] == "ok"


def test_meta(client):
    resp = client.get("/api/meta")
    assert resp.status_code == 200
    assert "sentiment" in resp.json()["tasks"]


def test_upload_csv_and_profile(client, sample_csv):
    resp = client.post(
        "/api/datasets/upload",
        files={"file": ("posts.csv", io.BytesIO(sample_csv), "text/csv")},
    )
    assert resp.status_code == 201, resp.text
    dataset = resp.json()
    assert dataset["records"] == 120
    assert dataset["status"] == "VALIDATED"
    assert dataset["column_map"].get("text") == "text"
    assert dataset["column_map"].get("username") == "username"

    profile = client.get(f"/api/datasets/{dataset['id']}/profile").json()["profile"]
    assert profile["records"] == 120
    assert profile["columns_count"] >= 10
    assert "missing_values" in profile
    assert profile["platform_distribution"].get("x") == 120
    assert profile["unique_users"] == 40
    assert profile["date_range"] is not None
    assert "sentiment_distribution" in profile
    assert "label" in profile["class_distributions"]


def test_upload_invalid_extension(client):
    resp = client.post(
        "/api/datasets/upload",
        files={"file": ("malware.exe", io.BytesIO(b"MZ binary"), "application/octet-stream")},
    )
    assert resp.status_code == 422
    assert "Unsupported file type" in resp.json()["detail"]


def test_upload_empty_file(client):
    resp = client.post(
        "/api/datasets/upload",
        files={"file": ("empty.csv", io.BytesIO(b""), "text/csv")},
    )
    assert resp.status_code == 422
    assert "empty" in resp.json()["detail"].lower()


def test_upload_invalid_csv_content(client):
    resp = client.post(
        "/api/datasets/upload",
        files={"file": ("broken.csv", io.BytesIO(b"\x00\x01\x02\x03"), "text/csv")},
    )
    # Unparseable binary garbage must not crash the API
    assert resp.status_code in {201, 422}
    if resp.status_code == 422:
        assert "detail" in resp.json()


def test_column_mapping_roundtrip(client, uploaded_dataset):
    ds_id = uploaded_dataset["id"]
    resp = client.post(
        f"/api/datasets/{ds_id}/column-map",
        json={"mapping": {"platform": "platform", "label": "label"}},
    )
    assert resp.status_code == 200
    assert resp.json()["column_map"]["platform"] == "platform"


def test_preprocess_creates_new_version(client, uploaded_dataset):
    ds_id = uploaded_dataset["id"]
    resp = client.post(
        f"/api/datasets/{ds_id}/preprocess",
        json={"options": {"deduplicate": True, "feature_engineering": True}},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    child = body["dataset"]
    assert child["id"] != ds_id
    assert child["version"] == 2
    assert child["parent_id"] == ds_id
    assert child["status"] == "PREPROCESSED"
    assert "text_clean" in child["column_names"]
    assert "engagement_score" in child["column_names"]
    steps = [s["step"] for s in body["report"]["steps"]]
    assert "text_cleaning" in steps and "feature_engineering" in steps


def test_rows_query_search_sort_paginate(client, uploaded_dataset):
    ds_id = uploaded_dataset["id"]
    resp = client.get(
        f"/api/datasets/{ds_id}/rows",
        params={"search": "SHOCKING", "page": 1, "page_size": 10},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] > 0
    assert all("SHOCKING" in r["text"] for r in body["items"])

    resp2 = client.get(
        f"/api/datasets/{ds_id}/rows",
        params={"sort_by": "likes", "sort_order": "desc", "page_size": 5},
    )
    likes = [r["likes"] for r in resp2.json()["items"]]
    assert likes == sorted(likes, reverse=True)


def test_dataset_delete_soft(client, uploaded_dataset):
    ds_id = uploaded_dataset["id"]
    resp = client.delete(f"/api/datasets/{ds_id}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True
    listing = client.get("/api/datasets").json()
    assert ds_id not in [d["id"] for d in listing["items"]]


def test_dataset_not_found(client):
    resp = client.get("/api/datasets/doesnotexist")
    assert resp.status_code == 404
