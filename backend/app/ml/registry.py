"""Model registry: versioned, joblib-serialized model artifacts."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import joblib
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.model_registry import ModelRecord
from app.utils.errors import NotFoundError

logger = logging.getLogger(__name__)

TASK_ABBR = {
    "sentiment": "SENT",
    "bot_detection": "BOT",
    "misinformation": "MIS",
    "topic_model": "TOP",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def next_version(db: Session, task: str) -> int:
    records = list(
        db.scalars(select(ModelRecord).where(ModelRecord.task == task)).all()
    )
    return max([r.version for r in records] or [0]) + 1


def create_record(
    db: Session,
    *,
    name: str,
    task: str,
    dataset_id: str | None,
    model_type: str,
    metrics: dict,
    features: list[str],
    artifact: dict,
    status: str = "TRAINED",
) -> ModelRecord:
    settings.ensure_dirs()
    version = next_version(db, task)
    model_id = f"MDL-{TASK_ABBR.get(task, 'GEN')}-{version:03d}"
    task_dir = settings.model_dir / task
    task_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = task_dir / f"{model_id}.joblib"

    artifact = {
        **artifact,
        "model_id": model_id,
        "name": name,
        "task": task,
        "model_type": model_type,
        "version": version,
        "dataset_id": dataset_id,
        "metrics": metrics,
        "features": features,
        "trained_at": _now(),
    }
    joblib.dump(artifact, artifact_path)

    record = ModelRecord(
        model_id=model_id,
        name=name,
        task=task,
        dataset_id=dataset_id,
        version=version,
        metrics=metrics,
        features=features,
        artifact_path=str(artifact_path),
        status=status,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    logger.info("Registered model %s (%s v%d)", model_id, task, version)
    return record


def list_models(db: Session, task: str | None = None) -> list[ModelRecord]:
    stmt = select(ModelRecord).order_by(ModelRecord.created_at.desc())
    if task:
        stmt = stmt.where(ModelRecord.task == task)
    return list(db.scalars(stmt).all())


def get_model(db: Session, model_ref: str) -> ModelRecord:
    record = db.get(ModelRecord, model_ref) or db.scalar(
        select(ModelRecord).where(ModelRecord.model_id == model_ref)
    )
    if not record:
        raise NotFoundError("Model not found.")
    return record


def get_active(db: Session, task: str) -> ModelRecord | None:
    return db.scalar(
        select(ModelRecord)
        .where(ModelRecord.task == task, ModelRecord.status == "ACTIVE")
        .order_by(ModelRecord.version.desc())
    )


def activate(db: Session, model_ref: str) -> ModelRecord:
    record = get_model(db, model_ref)
    for other in list(
        db.scalars(
            select(ModelRecord).where(
                ModelRecord.task == record.task, ModelRecord.status == "ACTIVE"
            )
        ).all()
    ):
        other.status = "ARCHIVED"
        db.add(other)
    record.status = "ACTIVE"
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def archive(db: Session, model_ref: str) -> ModelRecord:
    record = get_model(db, model_ref)
    record.status = "ARCHIVED"
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def load_artifact(record: ModelRecord) -> dict:
    path = Path(record.artifact_path)
    if not path.exists():
        raise NotFoundError(
            f"Model artifact for {record.model_id} is missing from disk."
        )
    return joblib.load(path)


def active_artifact(db: Session, task: str) -> dict | None:
    """Return the ACTIVE model artifact for a task, or None if not trained."""
    record = get_active(db, task)
    if not record:
        return None
    try:
        return load_artifact(record)
    except Exception as exc:  # pragma: no cover
        logger.error("Failed to load artifact for %s: %s", record.model_id, exc)
        return None
