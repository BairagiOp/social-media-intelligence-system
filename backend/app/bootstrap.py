"""App bootstrap: sample data generation, ingestion and baseline model training.

Runs once at startup (configurable via SMDPIS_AUTO_BOOTSTRAP). All work happens
in a background thread so API startup is never blocked. Nothing here fabricates
results — models are genuinely trained on the generated sample dataset.
"""
from __future__ import annotations

import logging
import subprocess
import sys
import threading
from pathlib import Path

from app.app_state import bootstrap_state
from app.config import settings
from app.ml import registry

logger = logging.getLogger(__name__)

SAMPLE_FILENAME = "smdp_posts.csv"
SAMPLE_PATH = settings.sample_dir / SAMPLE_FILENAME
GENERATOR_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "generate_sample_data.py"


class _QuietJob:
    """Minimal job shim so trainer.run_training can report progress."""

    def __init__(self):
        self.steps: list[tuple[str, int, str]] = []

    def step(self, name: str, progress: int, detail: str = "") -> None:
        self.steps.append((name, progress, detail))
        logger.info("Bootstrap training %s (%s%%) %s", name, progress, detail)


def ensure_sample_file(force: bool = False) -> Path:
    if SAMPLE_PATH.exists() and not force:
        return SAMPLE_PATH
    settings.sample_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            sys.executable,
            str(GENERATOR_SCRIPT),
            "--output",
            str(settings.sample_dir),
            "--posts",
            "10000",
            "--accounts",
            "1000",
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0 or not SAMPLE_PATH.exists():
        raise RuntimeError(
            f"Sample data generation failed: {result.stderr[-800:]}"
        )
    return SAMPLE_PATH


def ensure_sample_dataset(db):
    """Generate + ingest the sample dataset if not already registered."""
    from app.services import dataset_service

    datasets = dataset_service.list_datasets(db)
    for d in datasets:
        if d.filename == SAMPLE_FILENAME and d.status != "DELETED" and d.version == 1:
            return d
    path = ensure_sample_file()
    dataset = dataset_service.ingest_existing_file(
        db, path, name="SMDPIS Synthetic Sample", source="sample"
    )
    logger.info("Sample dataset ingested: %s", dataset.id)
    return dataset


def _train_if_needed(db, task: str, dataset_id: str, params: dict) -> None:
    from app.ml import jobs as job_manager
    from app.ml import trainer as trainer_module

    if registry.get_active(db, task):
        logger.info("Bootstrap: task %s already has an active model.", task)
        return
    full_params = {"dataset_id": dataset_id, "task": task, **params}
    job = _QuietJob()
    record = trainer_module.run_training(db, job, full_params)
    registry.activate(db, record.model_id)
    logger.info("Bootstrap: trained and activated %s", record.model_id)


def run_bootstrap() -> None:
    from app.database import SessionLocal

    bootstrap_state.step("start", "RUNNING", "Initializing sample environment")
    db = SessionLocal()
    try:
        bootstrap_state.step("sample_file", "RUNNING", "Generating synthetic dataset")
        ensure_sample_file()
        bootstrap_state.step("sample_file", "DONE", "Sample dataset ready")

        bootstrap_state.step("ingest", "RUNNING", "Registering sample dataset")
        dataset = ensure_sample_dataset(db)
        bootstrap_state.step("ingest", "DONE", f"Dataset {dataset.id}")

        bootstrap_state.step("models", "RUNNING", "Training baseline models")
        _train_if_needed(
            db, "sentiment", dataset.id,
            {"target": "label", "model_type": "logistic_regression"},
        )
        _train_if_needed(
            db, "bot_detection", dataset.id,
            {"target": "is_automated", "model_type": "random_forest"},
        )
        _train_if_needed(
            db, "misinformation", dataset.id,
            {"target": "misinfo_label", "model_type": "logistic_regression"},
        )
        _train_if_needed(
            db, "topic_model", dataset.id,
            {"n_topics": 6, "model_type": "nmf"},
        )
        bootstrap_state.step("models", "DONE", "Baseline models active")
        bootstrap_state.step("complete", "DONE", "Bootstrap complete")
    except Exception as exc:
        logger.exception("Bootstrap failed")
        bootstrap_state.step("error", "ERROR", str(exc))
    finally:
        db.close()


def start_background_bootstrap() -> None:
    if not settings.auto_bootstrap:
        bootstrap_state.status = "SKIPPED"
        return
    thread = threading.Thread(
        target=run_bootstrap, daemon=True, name="smdpis-bootstrap"
    )
    thread.start()
