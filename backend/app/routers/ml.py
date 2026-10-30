"""ML training, jobs and model registry endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.ml import jobs as job_manager
from app.ml import registry
from app.ml.trainer import TASKS
from app.schemas import JobOut, ModelListResponse, ModelOut, TaskCatalogResponse, TrainRequest
from app.utils.errors import NotFoundError

router = APIRouter(prefix="/api/ml", tags=["ml"])


@router.get("/tasks", response_model=TaskCatalogResponse)
def task_catalog():
    return TaskCatalogResponse(tasks=TASKS)


@router.post("/train", response_model=JobOut, status_code=202)
def train(body: TrainRequest, db: Session = Depends(get_db)):
    # Validate dataset exists before spawning the job.
    from app.services import dataset_service

    dataset_service.get_dataset(db, body.dataset_id)
    params = body.model_dump()
    job = job_manager.start_training(params)
    return JobOut(**job.to_dict())


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(limit: int = Query(20, ge=1, le=100)):
    return [JobOut(**j.to_dict()) for j in job_manager.list_jobs(limit)]


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise NotFoundError("Training job not found.")
    return JobOut(**job.to_dict())


@router.get("/models", response_model=ModelListResponse)
def list_models(task: str | None = None, db: Session = Depends(get_db)):
    records = registry.list_models(db, task=task)
    return ModelListResponse(
        items=[ModelOut(**r.to_dict()) for r in records], total=len(records)
    )


@router.get("/models/{model_ref}", response_model=ModelOut)
def get_model(model_ref: str, db: Session = Depends(get_db)):
    record = registry.get_model(db, model_ref)
    return ModelOut(**record.to_dict())


@router.post("/models/{model_ref}/activate", response_model=ModelOut)
def activate_model(model_ref: str, db: Session = Depends(get_db)):
    record = registry.activate(db, model_ref)
    return ModelOut(**record.to_dict())


@router.post("/models/{model_ref}/archive", response_model=ModelOut)
def archive_model(model_ref: str, db: Session = Depends(get_db)):
    record = registry.archive(db, model_ref)
    return ModelOut(**record.to_dict())


@router.get("/active")
def active_models(db: Session = Depends(get_db)):
    out = {}
    for task in TASKS:
        record = registry.get_active(db, task)
        out[task] = record.to_dict() if record else None
    return out
