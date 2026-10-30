"""Shared CLI runner for the SMDPIS training scripts."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.database import SessionLocal, init_db  # noqa: E402
from app.ml import registry  # noqa: E402
from app.ml.trainer import run_training  # noqa: E402
from app.services import dataset_service  # noqa: E402


class PrintJob:
    """Job shim that prints trainer progress to stdout."""

    def step(self, name: str, progress: int, detail: str = "") -> None:
        print(f"  [{progress:>3}%] {name:<12} {detail}")


def ensure_dataset(db, source: str | None) -> str:
    """Return a dataset id: existing id, or ingest from a file path, or the sample."""
    if source is None:
        # Use the sample dataset (generate + ingest on demand).
        from app.bootstrap import ensure_sample_dataset

        dataset = ensure_sample_dataset(db)
        print(f"Using sample dataset: {dataset.id} ({dataset.records} records)")
        return dataset.id

    try:
        dataset = dataset_service.get_dataset(db, source)
        print(f"Using registered dataset: {dataset.id} ({dataset.records} records)")
        return dataset.id
    except Exception:
        path = Path(source)
        if not path.exists():
            raise SystemExit(f"Dataset '{source}' is neither an ID nor an existing file.")
        dataset = dataset_service.ingest_existing_file(db, path, source="training_script")
        print(f"Ingested dataset: {dataset.id} ({dataset.records} records)")
        return dataset.id


def main(task: str, default_params: dict) -> None:
    parser = argparse.ArgumentParser(description=f"Train SMDPIS {task} model")
    parser.add_argument("--dataset", default=None, help="Dataset ID or file path (default: sample)")
    parser.add_argument("--target", default=default_params.get("target"))
    parser.add_argument("--model-type", default=default_params.get("model_type"))
    parser.add_argument("--test-size", type=float, default=default_params.get("test_size", 0.2))
    parser.add_argument("--n-topics", type=int, default=default_params.get("n_topics", 6))
    parser.add_argument("--no-activate", action="store_true",
                        help="Do not activate the model after training")
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        dataset_id = ensure_dataset(db, args.dataset)

        params = {
            **default_params,
            "task": task,
            "dataset_id": dataset_id,
            "test_size": args.test_size,
            "n_topics": args.n_topics,
        }
        if args.target:
            params["target"] = args.target
        if args.model_type:
            params["model_type"] = args.model_type

        print(f"\n=== Training {task} ===")
        print(f"Params: {json.dumps({k: v for k, v in params.items()}, default=str)}")

        start = time.time()
        record = run_training(db, PrintJob(), params)
        elapsed = time.time() - start

        if not args.no_activate:
            registry.activate(db, record.model_id)

        # Save metrics artifact for evaluation reporting
        eval_dir = PROJECT_ROOT / "ml" / "evaluation"
        eval_dir.mkdir(parents=True, exist_ok=True)
        metrics_path = eval_dir / f"{task}_metrics.json"
        with open(metrics_path, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "model_id": record.model_id,
                    "task": record.task,
                    "dataset_id": dataset_id,
                    "metrics": record.metrics,
                    "elapsed_seconds": round(elapsed, 2),
                    "status": record.status,
                },
                fh,
                indent=2,
                default=str,
            )

        print("\n--- RESULTS ---")
        for key in ("accuracy", "precision", "recall", "f1", "roc_auc",
                    "n_topics", "reconstruction_error", "mean_document_topic_strength",
                    "train_size", "test_size", "accounts", "documents"):
            if key in record.metrics:
                print(f"{key:>32}: {record.metrics[key]}")
        if "confusion_matrix" in record.metrics:
            print(f"{'confusion_matrix':>32}: {record.metrics['confusion_matrix']}")
        if "feature_importance" in record.metrics:
            print(f"{'feature_importance':>32}: {record.metrics['feature_importance']}")
        print(f"{'model_id':>32}: {record.model_id}")
        print(f"{'artifact':>32}: {record.artifact_path}")
        print(f"{'status':>32}: {record.status}")
        print(f"{'metrics file':>32}: {metrics_path}")
        print(f"{'elapsed':>32}: {elapsed:.1f}s")
    finally:
        db.close()
