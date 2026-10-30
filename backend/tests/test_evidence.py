"""Evidence hashing and chain-of-custody tests."""
from __future__ import annotations

import hashlib
import io


def test_upload_creates_evidence_with_sha256(client, sample_csv):
    resp = client.post(
        "/api/datasets/upload",
        files={"file": ("evidence_test.csv", io.BytesIO(sample_csv), "text/csv")},
    )
    assert resp.status_code == 201
    dataset = resp.json()
    assert dataset["evidence_id"]

    ev_resp = client.get(f"/api/evidence/{dataset['evidence_id']}")
    assert ev_resp.status_code == 200
    evidence = ev_resp.json()
    expected = hashlib.sha256(sample_csv).hexdigest()
    assert evidence["sha256"] == expected
    assert evidence["size_bytes"] == len(sample_csv)
    assert evidence["dataset_id"] == dataset["id"]


def test_audit_log_sequence_and_integrity(client, uploaded_dataset):
    ev_id = uploaded_dataset["evidence_id"]
    resp = client.get(f"/api/evidence/{ev_id}/audit-log")
    assert resp.status_code == 200
    body = resp.json()
    events = [e["event"] for e in body["items"]]
    assert "UPLOAD" in events
    assert "HASH" in events
    assert "VALIDATE" in events
    # order: UPLOAD before HASH before first VALIDATE
    assert events.index("UPLOAD") < events.index("HASH") < events.index("VALIDATE")
    for event in body["items"]:
        assert len(event["signature"]) == 64  # HMAC-SHA256 hex
    assert body["integrity"]["verified"] is True


def test_preprocess_and_report_add_audit_events(client, uploaded_dataset):
    ev_id = uploaded_dataset["evidence_id"]
    client.post(
        f"/api/datasets/{uploaded_dataset['id']}/preprocess",
        json={"options": {}},
    )
    report = client.post(
        "/api/reports", json={"dataset_id": uploaded_dataset["id"], "title": "T"}
    )
    assert report.status_code == 201

    events = [
        e["event"]
        for e in client.get(f"/api/evidence/{ev_id}/audit-log").json()["items"]
    ]
    assert "PREPROCESS" in events
    assert "REPORT" in events


def test_evidence_export(client, uploaded_dataset):
    ev_id = uploaded_dataset["evidence_id"]
    resp = client.get(f"/api/evidence/{ev_id}/export")
    assert resp.status_code == 200
    body = resp.json()
    assert body["evidence"]["sha256"]
    assert body["integrity"]["verified"] is True
    assert len(body["audit_trail"]) >= 3
    assert "not modified" in body["statement"]


def test_evidence_list(client, uploaded_dataset):
    resp = client.get("/api/evidence")
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


def test_verify_endpoint_rehashes_and_checks_chain(client, uploaded_dataset):
    ev_id = uploaded_dataset["evidence_id"]
    resp = client.get(f"/api/evidence/{ev_id}/verify")
    assert resp.status_code == 200
    body = resp.json()
    assert body["evidence_id"] == ev_id
    assert body["valid"] is True
    assert body["file_integrity"]["verified"] is True
    assert body["file_integrity"]["recorded_sha256"] == body["file_integrity"]["current_sha256"]
    assert body["audit_chain"]["valid"] is True
    assert body["audit_chain"]["events_checked"] >= 3
    assert body["audit_chain"]["tampered"] == []
