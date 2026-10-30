"""In-memory training job manager (background threads with progress)."""
from __future__ import annotations

import logging
import threading
import traceback
import uuid
from datetime import datetime, timezone

from app.database import SessionLocal

logger = logging.getLogger(__name__)


class TrainingJob:
    def __init__(self, params: dict):
        self.id = uuid.uuid4().hex[:12]
        self.params = params
        self.status = "QUEUED"          # QUEUED | RUNNING | COMPLETE | FAILED
        self.progress = 0
        self.step_name = "queued"
        self.detail = ""
        self.error: str | None = None
        self.result: dict | None = None
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.lock = threading.Lock()

    def step(self, name: str, progress: int, detail: str = "") -> None:
        with self.lock:
            self.status = "RUNNING"
            self.step_name = name
            self.progress = max(self.progress, min(int(progress), 100))
            self.detail = detail

    def finish(self, result: dict) -> None:
        with self.lock:
            self.status = "COMPLETE"
            self.progress = 100
            self.step_name = "complete"
            self.result = result

    def fail(self, message: str) -> None:
        with self.lock:
            self.status = "FAILED"
            self.error = message

    def to_dict(self) -> dict:
        with self.lock:
            return {
                "job_id": self.id,
                "task": self.params.get("task"),
                "dataset_id": self.params.get("dataset_id"),
                "status": self.status,
                "progress": self.progress,
                "step": self.step_name,
                "detail": self.detail,
                "error": self.error,
                "result": self.result,
                "created_at": self.created_at,
            }


JOBS: dict[str, TrainingJob] = {}


def start_training(params: dict) -> TrainingJob:
    from app.ml import trainer as trainer_module

    job = TrainingJob(params)
    JOBS[job.id] = job

    def _run():
        job.step("validate", 5, "Starting")
        db = SessionLocal()
        try:
            record = trainer_module.run_training(db, job, params)
            job.finish(
                {
                    "model": record.to_dict(),
                }
            )
        except Exception as exc:
            logger.error("Training failed: %s", traceback.format_exc())
            message = getattr(exc, "message", None) or str(exc)
            job.fail(message)
        finally:
            db.close()

    thread = threading.Thread(target=_run, daemon=True, name=f"train-{job.id}")
    thread.start()
    return job


def get_job(job_id: str) -> TrainingJob | None:
    return JOBS.get(job_id)


def list_jobs(limit: int = 20) -> list[TrainingJob]:
    return list(JOBS.values())[-limit:]
