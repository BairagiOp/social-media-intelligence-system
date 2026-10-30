"""Pytest configuration: isolated temp database/storage, no auto-bootstrap."""
from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path

import pytest

# --- Environment must be configured BEFORE the app is imported -------------
_TMP = Path(tempfile.mkdtemp(prefix="smdpis_test_"))
os.environ["SMDPIS_DATABASE_URL"] = f"sqlite:///{_TMP / 'test.db'}"
os.environ["SMDPIS_DATA_DIR"] = str(_TMP / "data")
os.environ["SMDPIS_MODEL_DIR"] = str(_TMP / "models")
os.environ["SMDPIS_AUTO_BOOTSTRAP"] = "false"
os.environ["SMDPIS_SECRET_KEY"] = "test-secret-key"
os.environ.setdefault("SMDPIS_ENV", "test")

from fastapi.testclient import TestClient  # noqa: E402

from app.database import init_db  # noqa: E402


@pytest.fixture(scope="session")
def app_instance():
    init_db()
    from app.main import app

    return app


@pytest.fixture(scope="session")
def client(app_instance):
    with TestClient(app_instance) as test_client:
        yield test_client


SAMPLE_CSV_HEADER = (
    "post_id,user_id,username,platform,text,timestamp,likes,comments,shares,"
    "followers,following,account_age,label,misinfo_label,is_automated,"
    "reply_to_username,shared_from_username\n"
)


def make_sample_csv(rows: int = 120) -> bytes:
    """Deterministic mini dataset covering every ML task."""
    lines = [SAMPLE_CSV_HEADER]
    for i in range(rows):
        # 40 distinct accounts so bot detection clears its 40-account minimum.
        user = f"user{(i % 40) + 1:02d}"
        is_bot = 1 if (i % 40) + 1 <= 6 else 0
        label = ["positive", "neutral", "negative"][i % 3]
        misinfo = 1 if i % 7 == 0 else 0
        if misinfo:
            text = f"SHOCKING claim {i} about topic{i % 5} going viral share now"
        elif is_bot:
            text = f"Amazing deal {i % 5} click link now #promo https://shop.example/{i}"
        elif label == "positive":
            text = f"Really love the new feature release {i} great work team #tech"
        elif label == "negative":
            text = f"Terrible experience {i} very disappointed with the update #fail"
        else:
            text = f"Update {i} about topic{i % 5} details posted here #news"
        if i % 5 == 0:
            text += f" @user{((i + 1) % 40) + 1:02d}"
        lines.append(
            f"P{i:04d},U{(i % 40) + 1:03d},{user},x,"
            f'"{text}",2024-0{i % 9 + 1}-1{i % 9} 1{i % 9}:00:00,'
            f"{i % 50},{i % 7},{i % 5},"
            f"{(300 if is_bot else 1000) + i},"
            f"{(2000 if is_bot else 200) + i},"
            f"{(60 if is_bot else 1000) + i},"
            f"{label},{misinfo},{is_bot},,\n"
        )
    return "".join(lines).encode("utf-8")


@pytest.fixture()
def sample_csv() -> bytes:
    return make_sample_csv()


@pytest.fixture()
def uploaded_dataset(client, sample_csv):
    resp = client.post(
        "/api/datasets/upload",
        files={"file": ("mini_posts.csv", io.BytesIO(sample_csv), "text/csv")},
        data={"name": "Mini test dataset"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()
